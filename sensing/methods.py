import numpy
import numpy.linalg
import scipy.linalg

class EnergyDetector:
	SLUG = 'ed'

	def __init__(self):
		pass

	def __call__(self, x):
		return numpy.sum(x**2)

class CovarianceDetector:
	def __init__(self, L=10):
		self.L = L

	def R(self, x):
		x0 = x - numpy.mean(x)

		L = self.L
		Ns = len(x0)

		lbd = numpy.empty(L)
		for l in xrange(L):
			if l > 0:
				xu = x0[:-l]
			else:
				xu = x0

			lbd[l] = numpy.dot(xu, x0[l:])/(Ns-l)

		return scipy.linalg.toeplitz(lbd)

class CAVDetector(CovarianceDetector):
	SLUG = 'cav'

	def __call__(self, x):
		R = self.R(x)
		T1 = numpy.sum(numpy.abs(R))/self.L
		T2 = numpy.abs(R[0,0])
		return T1/T2

class CFNDetector(CovarianceDetector):
	SLUG = 'cfn'

	def __call__(self, x):
		R = self.R(x)
		T1 = numpy.sum(R**2.)/self.L
		T2 = R[0,0]**2.
		return T1/T2

class MACDetector(CovarianceDetector):
	SLUG = 'mac'

	def __call__(self, x):
		R = self.R(x)

		T1 = numpy.max(numpy.abs(R[0,1:]))
		T2 = numpy.abs(R[0,0])
		return T1/T2

class EigenvalueDetector(CovarianceDetector):
	def lbd(self, x):
		R = self.R(x)

		lbd = numpy.linalg.eigvalsh(R)
		return lbd.real

class MMEDetector(EigenvalueDetector):
	SLUG = 'mme'

	def __call__(self, x):
		lbd = self.lbd(x)
		lbd.sort()

		return lbd[-1]/lbd[0]

class EMEDetector(EigenvalueDetector):
	SLUG = 'eme'

	def __call__(self, x):
		lbd = self.lbd(x)
		lbd.sort()

		return numpy.sum(x**2)/lbd[0]

class AGMDetector(EigenvalueDetector):
	SLUG = 'agm'

	def __call__(self, x):
		lbd = self.lbd(x)

		return numpy.mean(lbd)/(numpy.prod(lbd)**(1/len(lbd)))

class METDetector(EigenvalueDetector):
	SLUG = 'met'

	def __call__(self, x):
		lbd = self.lbd(x)
		lbd.sort()

		return lbd[-1]/numpy.sum(lbd)
