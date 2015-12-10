import numpy
import numpy.linalg
import scipy.linalg

from sensing.utils import fam

class SNEISMTVDetector:
	SLUG = 'ed'

	def __init__(self, N):
		self.N = N

	def __call__(self, x):

		assert len(x) >= self.N
		x0 = x[:self.N]

		x_dbm = x0 * 3.3 * 1000. / 4095. / 25. - 84. - 66.
		x_w = 1e-3 * 10. ** (x_dbm / 10.)

		return numpy.sum(x_w)

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
		return numpy.abs(lbd)

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

		return numpy.mean(lbd)/(numpy.prod(lbd)**(1./len(lbd)))

class METDetector(EigenvalueDetector):
	SLUG = 'met'

	def __call__(self, x):
		lbd = self.lbd(x)
		lbd.sort()

		return lbd[-1]/numpy.sum(lbd)

class CyclostationaryDetector:
	def __init__(self, Np, L):
		self.Np = Np
		self.L = L

	def SCF(self, x):
		return fam(x, self.Np, self.L)

class SCFDetector(CyclostationaryDetector):
	SLUG = 'scf'

	def __call__(self, x):
		Sx = self.SCF(x)

		N = Sx.shape[1]/2
		Sx0 = numpy.tile(Sx[:,N].reshape((self.Np, 1)), (1, 2*N))
		T = numpy.abs(Sx/Sx0)

		h = numpy.max([numpy.max(T[:,:N]), numpy.max(T[:,N+1:])])
		return h

class CANDetector(CyclostationaryDetector):
	SLUG = 'can'

	def __call__(self, x):
		Sx = self.SCF(x)

		N = Sx.shape[1]/2
		T = numpy.abs(Sx)

		h = numpy.max([numpy.max(T[:,:N]), numpy.max(T[:,N+1:])])
		return h
