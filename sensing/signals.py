from vesna.rftest import usbtmc
import numpy

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

class Noise(SMBVGeneratorControl):

	SLUG = "noise"

	def get_wv_data(self, fs, x):

		MAX = 0x7fff

		x0 = numpy.asarray(x*MAX, numpy.dtype('<i2'))

		offs = -20*numpy.log10(numpy.std(x0)/MAX)

		assert offs > 0

		bin_data = x0.data

		crc = 0xa50f74ff+1
		crc ^= numpy.bitwise_xor.reduce(
				numpy.frombuffer(bin_data, numpy.dtype('<u4')))

		assert len(bin_data) % 4 == 0

		data = "{TYPE: SMU-WV,%d} " % (crc,)
		data += "{SAMPLES: %d} " % (len(bin_data)/4,)
		data += "{LEVEL OFFS: %.1f,0} " % (offs,)
		data += "{CLOCK: %d} " % (fs,)
		data += "{WAVEFORM-%d: #%s}" % (len(bin_data) + 1, bin_data)

		return data

	def set_waveform(self):
		N = 500000
		fs = 50000000

		noise = numpy.random.normal(scale=0.3, size=N*2)
		noise = numpy.clip(noise, -1., 1.)

		wv_data = self.get_wv_data(fs, noise)

		bin_len = "%d" % (len(wv_data),)

		assert len(bin_len) < 10

		cmd = "bb:arb:waveform:data '/var/user/data/noise.wv', #%d%s%s\n" % (
				len(bin_len), bin_len, wv_data)

		self.gen.write("system:comm:gpib:lter eoi\n")
		self.gen.write(cmd)
		self.gen.write("system:comm:gpib:lter standard\n")

		self.gen.write("bb:arb:wav:sel '/var/user/data/noise.wv'\n")
		self.gen.write("bb:arb:state on\n")

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
