import numpy
import timeit

def main():
	#x = numpy.random.normal(scale=3.3e-5, size=25000)
	#x = numpy.random.normal(scale=4.0e-5, size=25000)
	#x = numpy.random.normal(scale=7.8e-5, size=100000)

	methods = [ "EnergyDetector()" ]

	cls = [	"CAVDetector",
		"CFNDetector",
		"MACDetector",
		"MMEDetector",
		"EMEDetector",
		"AGMDetector",
		"METDetector" ]
	for c in cls:
		for L in xrange(5, 25, 5):
			methods.append("%s(L=%d)" % (c, L))

	for Ns in [25000, 50000, 100000]:
		for method in methods:
			tm = timeit.Timer(
				setup="""
import numpy
import sensing.methods
x = numpy.random.normal(scale=3.3e-5, size=%d)
det = sensing.methods.%s
""" % (Ns, method),

			stmt = "det(x)")

			N = 1000
			r = tm.repeat(repeat=10, number=N)
			t = min(r)/float(N)*1e6 # us/exc.

			print "%s\t%d\t%f" % (method, Ns, t)

main()
