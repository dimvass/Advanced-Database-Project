#!/usr/bin/env python3
import signal
import os
import threading
import socket
import sys
import select
import logging
import queue
#http://www.summet.com/dmsi/html/pymysql.html
import pymysql
import synchronisation

#message codes
#connect            0
#bid                4
#bid_item           5
#i_am_interested    6
#quit               7
#auction_complete   8
#duplicate_name     9
#start_bidding      10
#stop_bidding       11
#new_high_bid       12
#price_drop         14
#budget             16

def handler(signum, frame):
    a1.change_state(4)
    a2.change_state(4)

class _Auctioneer():
    def __init__(self,port,f,database,sync,configuration,dbi):
        logging.basicConfig(level=logging.DEBUG, format='(%(threadName)-3s) %(message)s')
        self.queue = queue
        self.sync = sync
        self.conf = configuration
        self.high_bid = -1              #current highest bid
        self.high_bidder = 'no_holder'  #current highest bidder
        self.no_bid_counter = 0         #number of rounds without bids
        self.connected_list = []        #list of connected users
        self.interested_list = []       #list of bidders interested in the current item
        self.bidder_socks = {}          #bidder id : socket
        self.wait = False                   #variable signifying that other server ended bidding for current item
        self.curr_item_id = -1          #item currently under bid
        self.next_avail_id = 0
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.sock.bind(('localhost', port))
        except (socket.error , msg):
            logging.debug(('Bind failed. Error Code : {0} Message {1}').format(str(msg[0]),msg[1]))
            sys.exit()
        #update auct_num file with port number    
        f.write('127.0.0.1 '+str(port)+'\n')
        f.close()
        self.sock.listen(10)
        self.connected_list.append(self.sock)
        self.db_ip = dbi[0]
        self.db_user = dbi[1]
        self.db_pass = dbi[2]
        (self.db,self.cursor) = self.connect_db(self.db_ip,self.db_user,self.db_pass,database)          #dont hack me please
        (self.fd,self.L,self.num_of_items) = self.init_items_list()
        self.conn_bidders = 0
        self.counter=0  #count the time outs and stop the bidding
        self.restart_countdown()
        self.state = 0  
                    #0: waiting for enough bidders to connect
                    #1: waiting L/1000 seconds for connections, then bid next item
                    #2: waiting i_am_interested for L/1000 seconds
                    #3: bidding
                    #4: exiting
                    #5: waiting for other server to finish bidding period

    def update(self,arg,arr):
        if arg == 0:
            self.conn_bidders = arr[0]
            if (self.conn_bidders > 1):
                self.change_state(1)
        elif arg == 1:
            self.duplicate_name(arr[0])
        elif arg == 2:
            if self.connect(arr[0],arr[1],arr[2]):
                self.sync.notify_remote_connection(self.conn_bidders,self)
                if (self.conn_bidders > 1):
                    self.change_state(1)
        elif arg == 3:
            bidd = arr[0]
            bidder = arr[1]
            self.wait = True
            if self.state == 3:
                if bidd > self.high_bid:
                    self.high_bid = bidd
                    self.high_bidder = bidder
        elif arg == 4:
            self.high_bid = arr[0]
            self.high_bidder = arr[1]
            self.new_high_bid()
            self.restart_countdown()

        elif arg == 5:
            name = arr[0]
            sock = arr[2]
            self.check_duplicate_remote(name,sock,arr)

    #check a bidder's name, connected in the other auctioneer, already exists in the local db
    #arg1: the bidder's name
    #arg2,3 needed to call not_duplicate_notify()
    def check_duplicate_remote(self,name,sock,arr):
        sql = 'SELECT Username FROM Users'
        self.cursor.execute(sql)
        for record in self.cursor:
            if name == record[0]:
                self.sync.notify_duplicate_name(sock,self)
                return
        self.sync.notify_not_duplicate(arr,self)

    #finds the bidders name which corresponds to the given Id
    #arg1: the bidder's Id
    def get_name(self,id):
        sql = 'SELECT Username FROM Users WHERE Id = (%s)'
        self.cursor.execute(sql,(str(id)))
        name = ''
        for record in self.cursor:
            name = record[0]
        return name

    #changes the auctioneer's state
    #arg1: the new state
    def change_state(self, st):
        self.state = st
        if st == 1:
            self.restart_countdown()
            self.wait = False

    #restarts the countdown
    def restart_countdown(self):
        self.countdown = self.L     

    #reads the timer value, and the item list form the conf file and stores in the db
    def init_items_list(self):
        fd = open(self.conf,'r')
        L = int(fd.readline().split()[0])/1000
        N = int(fd.readline().split()[0])
        for i in range(N):
            line = fd.readline().split()
            descr = " ".join(line[1:])
            price = float(line[0])
            sql = "INSERT INTO Items (Id, Description, Price) VALUES (%s, %s, %s)"
            self.cursor.execute(sql,(str(i),descr,price))
        self.db.commit()
        return (fd,L,N)

    #return next item's description and initial price
    def read_next_item(self):
        sql = 'SELECT * FROM Items WHERE Id = (%s)'
        self.cursor.execute(sql,(str(self.curr_item_id)))
        descr = ''
        price = -1
        for record in self.cursor:
            descr = record[1]
            price = record[2]
        return(price,descr)

    #called when a new bidder connects to an auctioneer
    #arg1: the bidder's name
    #arg2: the budget available for the bidder
    #arg2: the bidder's socket
    def connect(self,name,budget,sock):
        try:
            sql = 'INSERT INTO Users (Id, Username, Budget) VALUES (%s, %s, %s)'
            self.cursor.execute(sql,(str(self.next_avail_id),name,budget))
            self.db.commit()
        except pymysql.err.IntegrityError:
            self.duplicate_name(sock)
            return False
        self.bidder_socks.update({sock:self.next_avail_id})
        self.next_avail_id += 1
        self.conn_bidders += 1
        return True

    #called when a bidder expresses interest for an item
    #arg1: the bidder's socket
    def i_am_interested(self,sock):
        self.interested_list.append(sock)

    #called when my_bid is received
    #arg1: the amount bidded
    #arg2: the bidder's socket
    #arg2: the bidder's name
    def my_bid(self,amount,s,name):
        if s in self.interested_list:
            logging.debug('new bid: amount= ' + str(amount))
            if (amount > self.high_bid) or (amount >= self.high_bid and self.high_bidder == 'no_holder'):
                self.high_bid = amount
                self.high_bidder = name
                self.new_high_bid()
                return 1
        return 0

    #called when a bidder declares that is shutting down
    #arg1: the bidder's socket
    def quit(self,sock):
        self.connected_list.remove(sock)
        if sock in self.interested_list:
            self.interested_list.remove(sock)
        del_id = self.bidder_socks.pop(sock)
        self.conn_bidders -= 1

    #called when the auction has progressed to the next item
    def bid_item(self):
        #send to each bidder the info for the next item
        for bid in self.connected_list[1:]:
            bid.sendall(('5;'+ str(self.high_bid)+';'+self.descr+';').encode('utf-8'))

    #called when it is time to start the bidding process for the current item
    def start_bidding(self):
        #enable bidding for an item
        logging.debug('bidding has started')
        logging.debug('initial price ' + str(self.high_bid))
        for s in self.interested_list:
            s.sendall(('10;'+str(self.high_bid)+';').encode('utf-8'))

    #called when a bid is higher than the highest bid for the item
    def new_high_bid(self):
        #inform all interested bidders for the change
        for s in self.interested_list:
            s.sendall(('12;'+str(self.high_bid)+';').encode('utf-8'))

    #called when nobody bids on an item and the price is dropped by 10%
    def drop_price(self):
        self.high_bid = round(0.9 * self.high_bid,2)
        for s in self.interested_list:
            s.sendall(('14;'+str(self.high_bid)+';').encode('utf-8'))

    #called when the bidding process for the current item is over
    def stop_bidding(self):
        logging.debug('bidding has stopped')
        sql = 'SELECT Id FROM Users WHERE UserName = (%s)'
        self.cursor.execute(sql,(str(self.high_bidder)))
        uid = -1
        ubudget = -1
        for record in self.cursor:
            uid = record[0]
        sql = 'INSERT INTO Bought (UserId, ItemId, Amount) VALUES (%s, %s, %s)'
        self.cursor.execute(sql,(str(uid),self.curr_item_id,self.high_bid))
        sql = 'SELECT Budget FROM Users WHERE Id = %s'
        self.cursor.execute(sql,(str(uid)))
        for record in self.cursor:
            ubudget = record[0]
        sql = 'UPDATE Users SET Budget= %s WHERE Id = %s'
        self.cursor.execute(sql,(str(ubudget-self.high_bid),str(uid)))
        self.db.commit()        
        for s in self.interested_list:
            s.sendall(('11;'+self.high_bidder+';').encode('utf-8'))
        for sock,bidder_id in self.bidder_socks.items():
            if bidder_id == uid:
                sock.sendall(('16;'+str(ubudget-self.high_bid)+';').encode('utf-8'))

    #called when there are no more items
    def auction_complete(self):
        for bid in self.connected_list[1:]:
            bid.sendall(('8;').encode('utf-8'))

    #called when there already is a bidder with that name
    #arg1: the new bidder's socket
    def duplicate_name(self,sock):
        #send message to bidder with duplicate name
        sock.sendall(('9;').encode('utf-8'))
        self.connected_list.remove(sock)

    #make a connection to the auctioners database and delete all previous data
    #args: the credentials to connect to the database
    def connect_db(self,address,user,password,base):
        db = pymysql.connect(address,user,password,base)
        cursor = db.cursor()
        sql = 'DELETE FROM Users'
        cursor.execute(sql)
        sql = 'DELETE FROM Items'
        cursor.execute(sql)
        sql = 'DELETE FROM Bought'
        cursor.execute(sql)
        db.commit()
        return (db,cursor)

    def serviceloop(self):
        while True:
            read_sockets,write_sockets,error_sockets = select.select(self.connected_list,[],[],1)
            #timemout
            if not(read_sockets):
                self.timemout_occurred()
            #incoming data
            else:
                self.proccess_message(read_sockets)
            #bidding - stop_bidding after L/1000 seconds without high_bid
            if self.state == 5:
                if self.wait == True:
                    self.stop_bidding()
                    self.interested_list = []
                    self.high_bidder = 'no_holder'
                    self.no_bid_counter = 0 
                    self.change_state(1)            
            elif self.state == 4:
                self.auction_complete()
                for s in self.connected_list:
                    s.shutdown(socket.SHUT_RDWR)
                    s.close()
                return
                
    def timemout_occurred(self):
        logging.debug(self.countdown)
        self.countdown -= 1                
        #waiting L/1000 seconds for connections, then bid next item                
        if self.countdown == 0:
            if self.state == 1:
                if (self.num_of_items):
                    self.curr_item_id += 1
                    (self.high_bid,self.descr) = self.read_next_item()
                    self.num_of_items -= 1                          
                    self.bid_item()
                    self.change_state(2)
                    self.restart_countdown()
                else:
                    logging.debug('no more items. Exiting...')
                    self.change_state(4)
            elif self.state == 3:
                if (self.high_bidder != 'no_holder'):
                    self.sync.notify_countdown(self.high_bid,self.high_bidder,self)
                    if (self.wait == True):
                        self.change_state(1)
                        self.stop_bidding()
                        self.interested_list = []
                        self.high_bidder = 'no_holder'
                        self.no_bid_counter = 0
                    else:
                        self.change_state(5)
                else:
                    #special case without bids,need to repeat process 5 times
                    self.drop_price()
                    self.no_bid_counter +=1
                    self.restart_countdown()
                    if (self.no_bid_counter == 6):
                        self.interested_list = []
                        self.no_bid_counter = 0
                        self.sync.notify_countdown(self.high_bid,self.high_bidder,self)
                        if (self.wait == True):
                            self.change_state(1)
                            self.stop_bidding()
                        else:
                            self.change_state(5)
            #waiting i_am_interested for L/1000 seconds
            elif self.state == 2:
                if (len(self.interested_list) > 0):
                    self.start_bidding()                            
                    self.change_state(3)
                    self.restart_countdown()
                else:
                    self.sync.notify_countdown(self.high_bid,self.high_bidder,self)
                    if self.wait == True:
                        logging.debug('nobody interested, discarding item')
                        self.change_state(1)
                    else:
                        self.change_state(5)

    def proccess_message(self,read_sockets):
        for sock in read_sockets:
            if sock == self.sock:           #server socket: this means incoming connected
                conn, addr = sock.accept()
                self.connected_list.append(conn)
                #display client information 
                logging.debug(('Connected with {0} :{1}').format(addr[0],str(addr[1])))
            else:
                data = sock.recv(1024).decode('utf-8')
                #divide data parts by delimiter ;
                data = data.split(";")
                if data == ['']:
                    self.quit(sock)
                else:
#                    logging.debug(data)
                    if (data[0] == "0"):                            
                        self.sync.notify_check_duplicate(data[1],data[2],sock,self)
                    elif data[0] == "6":
                        if self.state == 2:
                            self.i_am_interested(sock)
                            logging.debug(('{0} joined the auction').format(self.get_name(self.bidder_socks[sock])))
                    elif data[0] == "4":
                        if self.state == 3:
                            self.changed = self.my_bid(float(data[1]),sock,self.get_name(self.bidder_socks[sock]))
                            if (self.changed):
                                self.sync.notify_high_bid(float(self.high_bid),self.high_bidder,self)
                            self.restart_countdown()
                    elif (data[0] == "7"):
                        logging.debug(('{0} quited').format(self.get_name(self.bidder_socks[sock])))
                        self.quit(sock)
                        if (len(self.bidder_socks) == 0):
                            if (self.curr_item_id == self.num_of_items):
                                self.change_state(4)
                            else:
                                self.change_state(1)
                        data = []

class Auctioneer(_Auctioneer):
    _instances = {}
    
    def __new__(cls, port, f ,database, sync, configuration, dbi):
        if port not in cls._instances:
            cls._instances[port] = _Auctioneer(port,f,database,sync,configuration,dbi)
        return cls._instances[port]   

def prepare_database_connection(f):
    fd = open(f,'r')
    db1 = []
    db2 = []
    for i in range(0,3):
        db1.append(fd.readline().split()[0])
    for i in range(0,3):
        db2.append(fd.readline().split()[0])
    return (db1,db2)
    
if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit('Usage: %s configuration_file database_info' % sys.argv[0])
    signal.signal(signal.SIGINT, handler)
    sync = synchronisation.Synchronisation()
    f1=open('auct_num_1','w')
    f2=open('auct_num_2','w')
    #declare threads
    conf = sys.argv[1]
    db_info = sys.argv[2]
    (db1,db2) = prepare_database_connection(db_info)
    a1 = Auctioneer(8888,f1,'advdb1',sync,conf,db1)
    a2 = Auctioneer(8889,f2,'advdb2',sync,conf,db2)
    sync.addObservers(a1,a2)
    t1 = threading.Thread(target=a1.serviceloop,name="One")
    t2 = threading.Thread(target=a2.serviceloop,name="Two")
    t1.start()
    t2.start()
