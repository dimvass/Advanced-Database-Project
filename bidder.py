#!/usr/bin/env python3

import socket
import sys
import select
import threading
import multiprocessing
import logging
import queue
import signal

#message codes
#connect            0
#list_description   1
#list_high_bid      2
#request_bid        3
#bid                4
#bid_item           5
#i_am_interested    6
#quit               7
#auction_complete   8
#duplicate_name     9
#start_bidding      10
#stop_bidding       11
#new_high_bid       12
#countdown          13
#price_drop         14
#check_duplicate    15
#budget             16
#is_duplicate       17
#not_duplicate      18

def handler(signum, frame):
    bidder.quit()
    sys.exit()

class Bidder():
    def __init__ (self, auctioneer_ip, port, name, budget, queue):
#        logging.basicConfig(level=logging.DEBUG, format='(%(threadName)-3s) %(message)s')
        self.queue = queue
        self.port = port
        self.name = name
        self.budget = budget
        try:
            #create an AF_INET, STREAM socket (TCP)
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        except (socket.error, msg):
            logging.debug(('Failed to create socket. Error code: {0}  ,Error message : {1}').format(str(msg[0]),msg[1]))
            sys.exit()
        #host = 'localhost'
        try:
            remote_ip = auctioneer_ip
        except socket.gaierror:
            logging.debug('Hostname could not be resolved. Exiting')
            sys.exit()
        try:
            self.sock.connect((remote_ip , port))
        except ConnectionRefusedError:
            #could not resolve
            logging.debug('Could not connect. Exiting')
            sys.exit()
        logging.debug(('Socket Connected to  ip {0}').format(remote_ip))
        self.connect()
        #initilisations
        self.cur_in_price = -1   #current initial price of an item
        self.cur_price = -1      #current highest bid
        self.cur_it_descr=''     #current item description
        
        #to receive data
        self.connection_list=[]
        self.connection_list.append(self.sock)
        #include stdin to capture user input
        self.connection_list.append(sys.stdin)

        self.state = 0  #0: connected to auctioner, waiting for item
                        #1: received info for item, not yet bidding
                        #2: bidding
                        #3: auction complete, exiting

    #called as the bidders first message to the auctioneer, sending him his name
    def connect(self):
        self.sock.sendall(('0;'+self.name+';'+str(self.budget)).encode('utf-8'))

    #called to make a new bid to the server
    #arg1: the server's socket
    #arg2: the amount to bid
    def bid(self, conn, amount):
        conn.sendall(('4;'+str(amount)+';').encode('utf-8'))

    #called by the user to print current highest bid
    def list_high_bid(self):
        logging.debug(str(self.cur_price))

    #called by the user to print the description of the current item
    def list_description(self):
        if (self.cur_it_descr!=''):
            logging.debug(self.cur_it_descr)

    #called when user wants to stop participating at the auction and shut down
    def quit(self):
        self.sock.sendall(('7;').encode('utf-8'))
        self.sock.close()
        sys.exit()

    #called to declare interest for the current item
    def i_am_interested(self):
        self.sock.sendall(('6;').encode('utf-8'))

    #called to save all information for the current item and present it to the server
    #arg1: the item's initial price
    #arg3: the item's description
    def bid_item(self, price, it_descr):
        self.cur_in_price = price
        self.cur_it_descr = it_descr
        logging.debug('The next item is:\n\t' + self.cur_it_descr + '\nand it has a starting price of:\n\t' + self.cur_in_price)

    #called when we receive start_bidding
    #arg: the initial price
    def start_bidding(self, init_pr):
        logging.debug('bidding has started')
        logging.debug('initial price ' + str(init_pr))
        self.cur_price = init_pr

    #called when we receive new_high_bid
    #arg: the amount
    def new_high_bid(self, amount):
        #print the new highest bid and related info
        logging.debug('new high bid')
        logging.debug('amount ' + str(amount))
        self.cur_price = amount

    #called when nobody bids on an item and the price is dropped by 10%
    #arg1: the new price
    def price_dropped(self, amount):
        #print the new highest bid and related info
        logging.debug('price dropped')
        logging.debug('new amount ' + str(amount))
        self.cur_price = amount

    #called when we receive stop_bidding
    #arg: the name of the highest bidder
    def stop_bidding(self, highest_bid):
        logging.debug('bidding has stopped')
        logging.debug('highest bidder ' + highest_bid)
        if (highest_bid == self.name):
            logging.debug('item bought')

    #called when the auctioneer reports that there are no items left and he is shutting down
    def auction_complete(self):
        logging.debug('The auction has been completed. Thank you for participating\n')
        self.sock.close()
        sys.exit()

    #called when the auctioneer reports that there is another bidder with the same name
    def duplicate_name(self):
        logging.debug('The name you entered already exists. Shutting down\n')
        self.sock.close()
        sys.exit()

    #changes the bidder's state
    #arg1: the new state
    def change_state(self, st):
        self.state = st

    def cmdloop(self):
        while True:
            try:
                read_sockets,write_sockets,error_sockets = select.select(self.connection_list,[],[],1)
                for sock in read_sockets:
                    #if there is data in stdin,there is no need for the process done for sockets
                    if (sock!=sys.stdin):
                        reply = sock.recv(4096).decode('utf-8')
                        #divide each argument using delimiter ';'
                        reply = reply.split(';')
                        #repeat process until there are no bytes left in the reply
                        while (reply!=[''] and reply!=[]):
#                            logging.debug(reply)
                            if (reply[0] == '5'):
                                #bid_item code
                                self.bid_item(reply[1],reply[2])
                                self.change_state(1)
                                logging.debug ('Press <Enter> to enter auction or wait for next item')
                                self.queue.put(0)       #notify parent process (driver)
                                reply = reply[4:]
                            elif (reply[0] == '8'):
                                #auction_complete code
                                self.auction_complete()
                                self.change_state(3)
                                reply = reply[1:]
                            elif (reply[0] == '9'):
                                #duplicate_name code
                                self.queue.put(2)       #notify parent process (driver)
                                self.duplicate_name()
                                reply = reply[1:]
                            elif (reply[0] == '10'):
                                #start_bidding code
                                self.start_bidding(float(reply[1]))
                                self.change_state(2)
                                logging.debug('Options\n1: item discription\n2: highest bid\n3 <amount>: new bid\nAvailable budget '+str(self.budget))                            
                                self.queue.put(1)       #notify parent process (driver)
                                reply = reply[2:]
                            elif (reply[0] == '11'):
                                #stop_bidding code
                                self.stop_bidding(reply[1])
                                self.change_state(0)
                                reply = reply[2:]
                                logging.debug('waiting for next item')
                            elif (reply[0] == '12'):
                                #new_high_bid code
                                self.new_high_bid(float(reply[1]))
                                reply = reply[2:]
                            elif (reply[0] == '14'):
                                #price_drop code
                                self.price_dropped(float(reply[1]))
                                reply = reply[2:]
                            elif (reply[0] == '16'):
                                #budget code
                                self.budget = float(reply[1])
                                reply = reply[2:]
                    else:
                        #read user input
                        if (self.state == 1):                        
                            line = sys.stdin.readline()
                            self.i_am_interested()
                        elif (self.state == 2):                            
                            line = sys.stdin.readline()
                            if line[0] == '1':
                                self.list_description()
                            elif line[0] == '2':
                                self.list_high_bid()
                            elif line[0] == '3':
                                line = line.split()
                                if (line != ['3']):
                                    try:
                                        amount = float(line[1])
                                    except ValueError:
                                        logging.debug('You didn\'t enter a number')
                                    else:
                                        self.bid(self.sock,amount)     #needs error checking

                            else:
                                logging.debug('invalid input')
            except KeyboardInterrupt:
                self.quit();
            except select.error:
                self.sock.close()
                sys.exit()    

if __name__ == "__main__":
    if len(sys.argv) < 5:
        sys.exit('Usage: %s auctioneer_ip port_num name budget' % sys.argv[0])
    signal.signal(signal.SIGINT, handler)
    queue = queue.Queue()
    bidder = Bidder(sys.argv[1],int(sys.argv[2]), sys.argv[3], sys.argv[4], queue)
    t1 = threading.Thread(target=bidder.cmdloop,name='bidder')
    t1.start()