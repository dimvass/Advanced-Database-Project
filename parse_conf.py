#!/usr/bin/env python3

f = open('conf','r')
L = f.readline()
L = L.split()
L = int(L[0])

N = f.readline()
N = N.split()
N = int(N[0])

itm={}

for i in range(0,N):
	a = f.readline()
	a = a.split()
	b = a[1:]
	b = " ".join(b)
	a = int(a[0])
	itm[b] = a

for descr,val in itm.items():
	print(str(val) + " " + descr )