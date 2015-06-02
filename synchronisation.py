import auctioneers

class Synchronisation():
	_singleton = None

	def __new__(cls, *args, **kwargs):
		if not cls._singleton:
			cls._singleton = super(Synchronisation, cls).__new__(cls, *args, **kwargs)
		return cls._singleton

	def __init__(self):
		self.observers = []

	def addObservers(self,auct1,auct2):
		self.observers.append(auct1)
		self.observers.append(auct2)

	def notifyObservers(self,arg,arr,caller):
		if caller == self.observers[0]:
			self.observers[1].update(arg,arr)
		elif caller == self.observers[1]:
			self.observers[0].update(arg,arr)
		else:
			print('invalid synchronisation caller')
			
	def notify_remote_connection(self,bidders,caller):
		self.notifyObservers(0,[bidders],caller)
	def notify_duplicate_name(self,sock,caller):
		self.notifyObservers(1,[sock],caller)
	def notify_not_duplicate(self,arr,caller):
		self.notifyObservers(2,arr,caller)
	def notify_countdown(self,bidd,bidder,caller):
		self.notifyObservers(3,[bidd,bidder],caller)
	def notify_high_bid(self,bidd,bidder,caller):
		self.notifyObservers(4,[bidd,bidder],caller)						
	def notify_check_duplicate(self,name,budget,sock,caller):
		self.notifyObservers(5,[name,budget,sock],caller)