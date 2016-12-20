Spectrum sensing methods
========================

Contents of this repository:

 * record.py

   Python script for performing measurements using a receiver connected to a
   vector signal generator. For example, USRP or receivers on VESNA sensor
   nodes. It varies the output power and receiver settings and records signal
   samples into files under a `samples-xxx` directory.

   To run:

       $ python record.py <experiment>

   Run without an argument to list available experiments.


 * simulate.py

   Python script for processing signal samples (from `record.py`) using various
   spectrum sensing test statistics (energy detection, cyclostationary,
   covariance based detection, etc.) and for performing simulations.

   To run:

       $ python simulate.py -f <experiment>

   Run with --help to see other available options.

   Output is written into a `simout-xxx` directory.

   This task can be parallelized in two ways:

    * `-p` sets the number of processes spawned by a single `simulate.py` invocation
    * `-s` can be used when multiple `simulate.py` invocations are working on
      the same dataset.


 * benchmark.py

   Python script for performing benchmarks.


 * sensing/methods.py

   Python module with implementations of several spectrum sensing
   methods.


 * sensing/siggen.py

   Python module with test signals that can be programmed into a
   Rohde&Schwarz vector signal generator.


 * sensing/signals.py

   Functions for calculating various signal samples. These are used for
   simulations.


 * measurements/

   Results of measurements using USRP, VESNA SNE-ISMTV-UHF and
   simulation.


 * analysis/

   Several IPython notebooks with descriptions of experiments and
   analyses of measurements.


For details, see "T. Solc, C. Fortuna: An Experimental Evaluation of Signal Detection Methods for Spectrum Sensing" (to be published)


License
=======

Spectrum sensing method experiments and implementations
Copyright (C) 2016  Tomaz Solc

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
