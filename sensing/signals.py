from vesna.rftest import usbtmc
import sys
import numpy
import scipy.signal

class GeneratorControl: pass

class SMBVGeneratorControl(GeneratorControl):
	def __init__(self, path="/dev/usbtmc3"):
		self.gen = usbtmc(path)
		self.gen.write("system:preset\n")

		self.set_waveform()

	def set(self, f, P):

		self.gen.write("freq %d Hz\n" % (f,))

		if P is None:
			self.gen.write("outp off\n")
		else:
			self.gen.write("pow %.1f dBm\n" % (P,))
			self.gen.write("outp on\n")

	def off(self):
		self.gen.write("outp off\n")

class ARBSMBVGeneratorControl(SMBVGeneratorControl):

	def _get_wv_data(self, fs, x):

		MAX = 0x7fff
		xs = numpy.clip(x, -1., 1.)*MAX

		x0 = numpy.empty(len(xs)*2, numpy.dtype('<i2'))
		x0[::2] = numpy.real(xs)
		x0[1::2] = numpy.imag(xs)

		xs2 = numpy.real(xs*numpy.conjugate(xs))
		rms_offs = 10.*numpy.log10(MAX**2/numpy.mean(xs2))
		peak_offs = 10.*numpy.log10(MAX**2/numpy.max(xs2))

		assert rms_offs >= 0

		bin_data = x0.data

		crc = 0xa50f74ff+1
		crc ^= numpy.bitwise_xor.reduce(
				numpy.frombuffer(bin_data, numpy.dtype('<u4')))

		assert len(bin_data) % 4 == 0

		data = "{TYPE: SMU-WV,%d} " % (crc,)
		data += "{SAMPLES: %d} " % (len(bin_data)/4,)
		data += "{LEVEL OFFS: %.1f,%.1f} " % (rms_offs, peak_offs)
		data += "{CLOCK: %d} " % (fs,)
		data += "{WAVEFORM-%d: #%s}" % (len(bin_data) + 1, bin_data)

		return data

	def set_arb_waveform(self, fs, x):
		wv_data = self._get_wv_data(fs, x)

		bin_len = "%d" % (len(wv_data),)

		assert len(bin_len) < 10

		cmd = "bb:arb:waveform:data '/var/user/data/noise.wv', #%d%s%s\n" % (
				len(bin_len), bin_len, wv_data)

		self.gen.write("system:comm:gpib:lter eoi\n")
		self.gen.write(cmd)
		self.gen.write("system:comm:gpib:lter standard\n")

		self.gen.write("bb:arb:wav:sel '/var/user/data/noise.wv'\n")
		self.gen.write("bb:arb:state on\n")

class Noise(ARBSMBVGeneratorControl):

	SLUG = "noise"

	def set_waveform(self):

		N = 500000
		fs = 50000000

		x = numpy.random.normal(scale=0.19, size=N*2)
		noise = x[::2] + complex(0, 1)*x[1::2]

		self.set_arb_waveform(fs, noise)

class CW(ARBSMBVGeneratorControl):

	SLUG = "cw"

	def __init__(self, dc=.5, **kwargs):
		self.dc = dc
		ARBSMBVGeneratorControl.__init__(self, **kwargs)

		self.SLUG = "cw_dc%d" % (dc*100,)

	def set_waveform(self):

		N = 10000
		fs = 10000000

		N1 = int(N * self.dc)
		N0 = N - N1

		x = numpy.concatenate( (numpy.ones(N1), numpy.zeros(N0)) )
		assert len(x) == N

		self.set_arb_waveform(fs, x)

class IEEEMic(SMBVGeneratorControl):
	def set_waveform(self):
		self.gen.write("fm:dev %d Hz\n" % (self.fdev,))
		self.gen.write("fm:source int\n")
		self.gen.write("lfo:freq %d Hz\n" % (self.fm,))
		self.gen.write("fm:state on\n")

class IEEEMicSoftSpeaker(IEEEMic):

	SLUG = "micsoft"

	fdev = 15000
	fm = 3900

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

def main():
	slug = sys.argv[1]

	for name, value in globals().iteritems():
		if hasattr(value, "SLUG") and value.SLUG == slug:
			print "Using GeneratorControl class", name
			value()
			return

	print "class with slug", slug, "not found!"

if __name__ == "__main__":
	main()
