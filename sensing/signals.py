import numpy
import scipy.signal
import os

class SimulatedIEEEMicSoftSpeaker:
	SLUG = "micsoft"

	fdev = 15000
	fm = 3900

	def get_sig(self, N, fs, fmic):

		n = numpy.arange(N)
		t = n/fs

		if fmic is None:
			fmic = fs/4.

		ph = 2.0*numpy.pi*fmic*t + self.fdev/self.fm * numpy.cos(2.0*numpy.pi*self.fm*t)
		x = numpy.cos(ph)

		return x

	def get(self, N, fc, fs, Pgen, fmic=None):

		if Pgen is None:
			x = numpy.zeros(N)
		else:
			x = self.get_sig(N, fs, fmic)
			x /= numpy.std(x)
			x *= 10.**(Pgen/20.)

		return x

class SimulatedNoise:
	SLUG = "noise"

	def get(self, N, fc, fs, Pgen):
		A = 10.**(Pgen/20.)
		x = numpy.random.normal(loc=0, scale=A, size=N)
		return x

class AddSpuriousCosine:
	def __init__(self, signal, fn, Pn):
		self.signal = signal
		self.An = 10.**(Pn/20.)
		self.fn = fn
		self.SLUG = "%s_spurious_%dkhz_%ddbm" % (signal.SLUG, fn/1e3, Pn)
		self.SLUG = self.SLUG.replace('-','m')

	def _get(self, N, fs):
		ph = 2. * numpy.pi * numpy.arange(N) * self.fn / fs
		xn = numpy.cos(ph)
		xn *= self.An / numpy.std(xn)
		return xn

	def get(self, N, fc, fs, Pgen):
		xs = self.signal.get(N, fc, fs, Pgen)
		xn = self._get(N, fs)

		return xs + xn

class AddGaussianNoise:
	def __init__(self, signal, Pn):
		self.signal = signal
		self.An = 10.**(Pn/20.)
		self.SLUG = "%s_gaussian_noise_%ddbm" % (signal.SLUG, Pn)
		self.SLUG = self.SLUG.replace('-','m')

	def get(self, N, fc, fs, Pgen):
		xs = self.signal.get(N, fc, fs, Pgen)
		xn = numpy.random.normal(loc=0, scale=self.An, size=N)

		return xs + xn

class Oversample:
	def __init__(self, signal, k):
		self.signal = signal
		self.k = k

		self.SLUG = "%s_ddc_%d" % (signal.SLUG, k)

	def get(self, N, fc, fs, Pgen, Pnoise=-100):

		if Pgen is None:
			xd = numpy.zeros(N)
		else:
			x = self.signal.get_sig(N*self.k, fs*self.k, fmic=fs/4)
			x *= 10.**(Pgen/20.) / numpy.std(x)

			if self.k == 1:
				xd = x
			else:
				xd = scipy.signal.decimate(x, self.k)

			assert len(xd) == N

		n = numpy.random.normal(loc=0, scale=1, size=N*self.k)
		if self.k == 1:
			nd = n
		else:
			nd = scipy.signal.decimate(n, self.k)
		nd *= 10.**(Pnoise/20.) / numpy.std(nd)

		assert len(nd) == N

		return xd + nd

class Divide:
	def __init__(self, signal, Nb):
		self.signal = signal
		self.Nb = Nb

		self.SLUG = signal.SLUG

	def get(self, N, *args, **kwargs):
		assert N % self.Nb == 0

		x = numpy.empty(N)
		for n in xrange(N/self.Nb):
			x[n*self.Nb:(n+1)*self.Nb] = self.signal.get(self.Nb, *args, **kwargs)

		return x

class LoadMeasurement:
	def __init__(self, template, Np):
		self.template = template
		self.Np = Np

		bn = os.path.basename(template)
		self.SLUG = '_'.join(bn.split('_')[:2])

	def get(self, N, fc, fs, Pgen):

		if Pgen is None:
			m = "off"
		else:
			m = '%.1fdbm' % (Pgen,)
			m = m.replace('-','m')
			m = m.replace('.','_')

		path = self.template % {
				'Pgen': m,
				'fs': "%.0f" % (fs/1e6),
				'Ns': N/self.Np/1000 }

		x = numpy.load(path)

		assert len(x) >= N

		return x[:N]
