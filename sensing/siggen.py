from vesna.rftest import usbtmc
import sys
import numpy as np

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
		xs = np.clip(x, -1., 1.)*MAX

		x0 = np.empty(len(xs)*2, np.dtype('<i2'))
		x0[::2] = np.real(xs)
		x0[1::2] = np.imag(xs)

		xs2 = np.real(xs*np.conjugate(xs))
		rms_offs = 10.*np.log10(MAX**2/np.mean(xs2))
		peak_offs = 10.*np.log10(MAX**2/np.max(xs2))

		assert rms_offs >= 0

		bin_data = x0.data

		crc = 0xa50f74ff+1
		crc ^= np.bitwise_xor.reduce(
				np.frombuffer(bin_data, np.dtype('<u4')))

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

		x = np.random.normal(scale=0.19, size=N*2)
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

		x = np.concatenate( (np.ones(N1), np.zeros(N0)) )
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

def main():
	try:
		slug = sys.argv[1]
	except IndexError:
		print "Available signals:"

		for name, value in globals().iteritems():
			if hasattr(value, "SLUG"):
				print "   %s (%s)" % (value.SLUG, name)
	else:
		for name, value in globals().iteritems():
			if hasattr(value, "SLUG") and value.SLUG == slug:
				print "Using GeneratorControl class", name
				value()
				return

		print "class with slug", slug, "not found!"

if __name__ == "__main__":
	main()
