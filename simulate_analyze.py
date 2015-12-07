import glob
import numpy
import re
import sys
import os
from matplotlib import pyplot


def get_ccdf(x):
	xs = numpy.array(x)
	xs.sort()

	N = float(len(xs))
	P = numpy.arange(N)/N

	return xs, P

def get_gamma0(campaign_glob, Pfa=0.1):
	path = campaign_glob.replace("*", "off")
	gammaN = numpy.loadtxt(path)

	gammaN, Pd = get_ccdf(gammaN)
	gamma0 = numpy.interp(1. - Pfa, Pd, gammaN)

	return gamma0


def iterate_campaign(path):
	for fn in glob.glob(path):
		g = re.search("_m([0-9_]+)dbm\.dat$", fn)
		if g:
			Pg = -float(g.group(1).replace('_', '.'))
			gamma = numpy.loadtxt(fn)

			yield Pg, gamma

def get_campaign_g(path, gamma0):
	Pg = []
	Pd = []

	for Pg0, gamma in iterate_campaign(path):
		Pg.append(Pg0)
		Pd.append(numpy.mean(gamma > gamma0))

	Pg = numpy.array(Pg)
	Pd = numpy.array(Pd)

	Pga = Pg.argsort()
	Pd = Pd[Pga]
	Pg = Pg[Pga]

	return Pg, Pd

def get_campaign(path, gamma0):
	Pg, Pd = get_campaign_g(path, gamma0)

	Pin = Pg

	return Pin, Pd

def get_pinmin(campaign_glob, gamma0, Pdmin):

	Pin, Pd = get_campaign(campaign_glob, gamma0)

	figname = os.path.basename(campaign_glob).replace("_*.dat", ".png")
	figpath = "pinmin2/figures/" + figname

	pyplot.figure()
	pyplot.plot(Pin, Pd)
	pyplot.xlabel("Pin")
	pyplot.ylabel("Pd")
	pyplot.axis([None, None, 0, 1])
	pyplot.title(campaign_glob)
	pyplot.grid()
	pyplot.savefig(figpath)
	pyplot.close()

	Pinmin = numpy.interp(Pdmin, Pd, Pin, left=0, right=0)

	return Pinmin

def process_campaign(campaign_glob, fout):
	gamma0 = get_gamma0(campaign_glob)

	Pinmin = get_pinmin(campaign_glob, gamma0, .9)

	fout.write("%s\t%f\n" % (campaign_glob, Pinmin))

def main():
	dir = sys.argv[1]

	fout = open("pinmin2/%s_pinmin.dat" % (dir,), "w")
	for path in glob.glob("%s/*_off.dat" % (dir,)):
		campaign_glob = path.replace("_off.", "_*.")
		print campaign_glob
		process_campaign(campaign_glob, fout)

	fout.close()

if __name__ == '__main__':
	main()
