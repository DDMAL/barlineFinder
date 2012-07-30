"""
list_bar_lines.py

Lists the top and bottom co-ordinates of each bar line found in an
image of printed music. The output format is a space-delimited list

    top_x top_y bottom_x bottom_y

of bar lines ordered from top to bottom and left to right. New systems
are flagged by a special line containing only a tilde ('~'). The
filenames of the output are the same as the filename of the input with
the extension changed to '.bdat'.

Usage python list_bar_lines.py [OPTIONS] {FILENAME}

Options
  -h display this help message
  -i save intermediate computation data  
  -o DIRNAME directory root for saving output (default ./)
  -r DPI resolution in dots per inch of input image (default 400)
  -s use single-staff rather than double-staff systems
"""

__author__ = 'John Ashley Burgoyne and Ichiro Fujinaga, McGill University'
__copyright__ = 'Copyright (C) 2006 John Ashley Burgoyne and Ichiro Fujinaga'
__version__ = 1.0


import getopt
import os
import pickle
import sys
import Image
import gamera.core
import gamera.plugins.numeric_io
import gamera.plugins.pil_io
import gamera.toolkits.musicstaves
from scipy import *


def _peaks(signal, width=3):
    # Finds the indices of the peaks in a signal.
    out = zeros(shape(signal), bool)
    halfWidth = floor(width / 2)
    parity = width % 2
    peaks = zeros(shape(signal), bool)
    for i in range(1, len(signal) - 1):
        start = max(0, i - halfWidth)
        middle = i - start
        end = min(i + halfWidth + parity, len(signal))
        peaks[i] = argmax(signal[start:end]) == middle
    return where(peaks)


def _filtfilt(b, a, sig):
    # Filters a signal in each direction.
    forward = signal.lfilter(b, a, sig)
    backward = signal.lfilter(b, a, forward[::-1])
    return backward[::-1]


class BarlinerContext(object):
    """Context (intermediate and output directories) for an input image."""

    def __init__(self, outputDirectory, saveIntermediates):
        self.saveIntermediates = saveIntermediates
        self.outputDirectory = os.path.normpath(outputDirectory)
        self.stavesDirectory \
            = self._makeSubdirectory('staves')
        self.downsampledStavesDirectory \
            = self._makeSubdirectory('downsampledStaves')
        self.downsampledDirectory = self._makeSubdirectory('downsampled')
        self.downsampledKernelDirectory \
            = self._makeSubdirectory('downsampledKernel')
        self.downsampledConvolutionMapDirectory \
            = self._makeSubdirectory('downsampledConvolutionMap')
        self.systemsDirectory \
            = self._makeSubdirectory('systems')
        self.downsampledSystemsDirectory \
            = self._makeSubdirectory('downsampledSystems')
        self.barLinesDirectory \
            = self._makeSubdirectory('barLines')
        self.downsampledBarLinesDirectory \
            = self._makeSubdirectory('downsampledBarLines')
        self.barsDirectory \
            = self._makeSubdirectory('bars')
        self.downsampledBarsDirectory \
            = self._makeSubdirectory('downsampledBars')

    def _makeSubdirectory(self, name):
        # Create, if necessary, the named subdirectory.
        fullName = os.path.join(self.outputDirectory, name)
        if self.saveIntermediates and not os.path.isdir(fullName):
            os.mkdir(fullName)
        return fullName


class BarlinerStaff(object):
    """Simple record class to make Gamera staves picklable."""
    
    def __init__(self, staffno, yposlist, staffrect):
        self.staffno = staffno
        self.yposlist = asarray(yposlist)
        self.staffrect = asarray(staffrect)
    
    def resample(self, factor):
        return BarlinerStaff(self.staffno,
                             cast['i'](around(multiply(self.yposlist,
                                                       factor))),
                             cast['i'](around(multiply(self.staffrect,
                                                       factor))))


class BarlinerSystem(object):
    """Simple record class for staff systems."""

    def __init__(self, ypos, systemrect):
        self.ypos = ypos
        self.systemrect = asarray(systemrect)
        
    def resample(self, factor):
        return BarlinerSystem(int(round(factor * self.ypos)),
                              cast['i'](around(multiply(self.systemrect,
                                                        factor))))


class Barliner(object):
    """
    Holding object for an original music image and all potential
    intermediate and output images generated while finding barLines.
    """

    DPI = 72 # needs to be an integer to ensure proper indexing
    minMarginWidth = 1.0 # in inches
    maxLineSeparation = 0.1 # in inches
    minStaffSeparation = 0.25 # in inches
    minSystemSeparation = 1.5 # in inches
    minBarWidth = 4.0 / 6.0 # in inches
    coeffs = signal.butter(10, 8.0 / DPI, btype='high')
    maxBarLines = 10
    kernelAspectRatio = 10
    pad = 10

    def __init__(self, context, inputDPI, singleStaves, filename):
        # Ensure proper float division.
        self.inputDPI = float(inputDPI)
        self.singleStaves = singleStaves
        tail = os.path.split(filename)[1]
        base = os.path.splitext(tail)[0]
        self.originalFilename \
            = os.path.normpath(filename)
        self.stavesFilename \
            = os.path.join(context.stavesDirectory, base + '.dat')
        self.downsampledStavesFilename \
            = os.path.join(context.downsampledStavesDirectory, base + '.dat')
        self.downsampledFilename \
            = os.path.join(context.downsampledDirectory, tail)
        self.downsampledKernelFilename \
            = os.path.join(context.downsampledKernelDirectory, base + '.dat')
        self.downsampledConvolutionMapFilename \
            = os.path.join(context.downsampledConvolutionMapDirectory,
                           base + '.dat')
        self.systemsFilename \
            = os.path.join(context.systemsDirectory, base + '.dat')
        self.downsampledSystemsFilename \
            = os.path.join(context.downsampledSystemsDirectory, base + '.dat')
        self.barLinesFilename \
            = os.path.join(context.barLinesDirectory, base + '.dat')
        self.downsampledBarLinesFilename \
            = os.path.join(context.downsampledBarLinesDirectory, base + '.dat')
        self.barsDirectory \
            = os.path.join(context.barsDirectory, base)
        self.downsampledBarsDirectory \
            = os.path.join(context.downsampledBarsDirectory, base)
        self.outputFilename \
            = os.path.join(context.outputDirectory, base + '.bdat')

    def getOriginal(self):
        return Image.open(self.originalFilename)

    def getStaves(self):
        if os.path.exists(self.stavesFilename):
            file = open(self.stavesFilename)
            staves = pickle.load(file)
            file.close()
            return staves

        def _staffClean(staves):

            def _separations(staves):
                return asarray([staff2.yposlist[2] - staff1.yposlist[2]
                                for staff1, staff2
                                in zip(staves[:-1], staves[1:])])

            separations = _separations(staves)
            threshold = mean(separations) + 2 * std(separations)
            if any(separations) > threshold:
                firstOffender = where(separations > threshold)[0]
                staves1 = staves2 = staves
                staves1[firstOffender] = []
                staves2[firstOffender + 1] = []
                separations1 = _separations(staves1)
                separations2 = _separations(staves2)
                staves = (staves1, staves2)[std(separations2)
                                            < std(separations1)]
                staves = _staffClean(staves)
            else:
                return staves

        gamera.core.init_gamera()
        image = gamera.core.load_image(self.originalFilename).to_onebit()
        ms = image.MusicStaves_rl_fujinaga()
        ms.remove_staves(crossing_symbols='all', num_lines=5)
        staves = [BarlinerStaff(staffobj.staffno,
                                staffobj.yposlist,
                                (staffobj.staffrect.ll_x,
                                 staffobj.staffrect.ll_y,
                                 staffobj.staffrect.ur_x,
                                 staffobj.staffrect.ur_y))
                  for staffobj in ms.get_staffpos()]
        staves = _staffClean(staves)
        if saveIntermediates:
            file = open(self.stavesFilename, 'w')
            pickle.dump(staves, file)
            file.close()
        return staves

    def getDownsampledStaves(self):
        if os.path.exists(self.downsampledStavesFilename):
            file = open(self.downsampledStavesFilename)
            staves = pickle.load(file)
            file.close()
            return staves
        multiplier = float(self.DPI) / self.inputDPI
        staves = [staff.resample(multiplier) for staff in self.staves]
        if saveIntermediates:
            file = open(self.downsampledStavesFilename, 'w')
            pickle.dump(staves, file)
            file.close()
        return staves            

    def getDownsampled(self):
        if os.path.exists(self.downsampledFilename):
            return misc.pilutil.imread(self.downsampledFilename, True)

        def _downsample(image):
            ratio = float(self.DPI) / self.inputDPI
            newImage = image.resize((int(round(ratio * image.size[0])),
                                     int(round(ratio * image.size[1]))),
                                    Image.ANTIALIAS)
            newImage = newImage.convert('L')
            return newImage

        image = _downsample(self.original)
        if saveIntermediates:
            image.save(self.downsampledFilename)
        return misc.pilutil.fromimage(image, True)

    def getDownsampledKernel(self):
        if os.path.exists(self.downsampledKernelFilename):
            file = open(self.downsampledKernelFilename)
            kernel = pickle.load(file)
            file.close()
            return kernel

        def _getKernel1(staves):
            yposlist = [0, 0, 0, 0, 0]
            for staff in staves:
                yposlist = add(yposlist, staff.yposlist)
            yposlist = cast['i'](around(cast['f'](yposlist) / len(staves)))
            yposlist = yposlist - yposlist[0]
            kernelHeight = yposlist[4] + 1
            kernelWidth = 4.0 * kernelHeight / self.kernelAspectRatio
            positiveSpace = 5 * kernelWidth + yposlist[4] + 1 - 5
            negativeSpace = kernelWidth * kernelHeight - positiveSpace
            multiplier = float(positiveSpace) / negativeSpace
            kernel = multiplier * ones((kernelHeight, kernelWidth), double)
            kernel[:, floor(kernelWidth * 0.5)] = -1
            kernel[yposlist, :] = -1
            return kernel

        def _getKernel2(staves):
            if len(staves) % 2 <> 0: staves = staves[:-1]
            yposlist = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
            for staff in staves:
                if staff.staffno % 2 == 0:
                    yposlist = concatenate((add(yposlist[:5],
                                                staff.yposlist),
                                            yposlist[-5:]))
                else:
                    yposlist = concatenate((yposlist[:5],
                                            add(yposlist[-5:],
                                                staff.yposlist)))
            yposlist = cast['i'](around(2 * cast['f'](yposlist) / len(staves)))
            yposlist = yposlist - yposlist[0]
            kernelHeight = yposlist[9] + 1
            kernelWidth = kernelHeight / self.kernelAspectRatio
            positiveSpace = 2 * (5 * kernelWidth + yposlist[4] + 1 - 5)
            negativeSpace \
                = 2 * (kernelWidth * (yposlist[4] + 1)) - positiveSpace
            multiplier = float(positiveSpace) / negativeSpace
            kernel = multiplier * ones((kernelHeight, kernelWidth), double)
            kernel[:, floor(kernelWidth * 0.5)] = -1
            kernel[yposlist, :] = -1
            kernel[yposlist[4]+1:yposlist[5], :] = 0
            return kernel

        staves = self.downsampledStaves
        if self.singleStaves:
            kernel = _getKernel1(staves)
        else:
            kernel = _getKernel2(staves)
        if saveIntermediates:
            file = open(self.downsampledKernelFilename, 'w')
            pickle.dump(kernel, file)
            file.close()
        return kernel

    def getDownsampledConvolutionMap(self):
        if os.path.exists(self.downsampledConvolutionMapFilename):
            file = open(self.downsampledConvolutionMapFilename)
            convolution = pickle.load(file)
            file.close()
            return convolution
        data = self.downsampled
        kernelData = self.downsampledKernel
        convolution = signal.convolve2d(data, kernelData, 'same')
        if saveIntermediates:
            file = open(self.downsampledConvolutionMapFilename, 'w')
            pickle.dump(convolution, file)
            file.close()
        return convolution

    def _getSystems(self, staves):
        leftBound = min([staff.staffrect[0] for staff in staves])
        rightBound = max([staff.staffrect[2] for staff in staves])
        if self.singleStaves:
            return [BarlinerSystem(staff.yposlist[2],
                                   (leftBound,
                                    staff.staffrect[1],
                                    rightBound,
                                    staff.staffrect[3]))
                    for staff in staves]
        else:
            return [BarlinerSystem(int(round(0.5 *
                                             (staff1.yposlist[2]
                                              + staff2.yposlist[2]))),
                                   (leftBound,
                                    staff2.staffrect[1],
                                    rightBound,
                                    staff1.staffrect[3]))
                    for staff1, staff2 in zip(staves[::2], staves[1::2])]
        
    def getSystems(self):
        if os.path.exists(self.systemsFilename):
            file = open(self.systemsFilename)
            systems = pickle.load(file)
            file.close()
            return systems
        staves = self.staves
        systems = self._getSystems(staves)
        if saveIntermediates:
            file = open(self.systemsFilename, 'w')
            pickle.dump(systems, file)
            file.close()
        return systems

    def getDownsampledSystems(self):
        if os.path.exists(self.downsampledSystemsFilename):
            file = open(self.downsampledSystemsFilename)
            systems = pickle.load(file)
            file.close()
            return systems
        staves = self.downsampledStaves
        systems = self._getSystems(staves)
        if saveIntermediates:
            file = open(self.downsampledSystemsFilename, 'w')
            pickle.dump(systems, file)
            file.close()
        return systems

    def getBarLines(self):
        if os.path.exists(self.barLinesFilename):
            file = open(self.barLinesFilename)
            barLineGroups = pickle.load(file)
            file.close()
            return barLineGroups
        ratio = float(self.inputDPI) / self.DPI
        bigBarLines = [cast['i'](around(multiply(barLines, ratio)))
                       for system, barLines in self.downsampledBarLines]
        barLineGroups = zip(self.systems, bigBarLines)
        if saveIntermediates:
            file = open(self.barLinesFilename, 'w')
            pickle.dump(barLineGroups, file)
            file.close()
        return barLineGroups

    def getDownsampledBarLines(self):
        if os.path.exists(self.downsampledBarLinesFilename):
            file = open(self.downsampledBarLinesFilename)
            barLineGroups = pickle.load(file)
            file.close()
            return barLineGroups
        rightEdge = self.downsampled.shape[1] - 1
        barLineGroups = list()
        for system in self.downsampledSystems:
            try:
                leftMargin = max(system.systemrect[0] - self.pad, 0)
                rightMargin = max(system.systemrect[2] + self.pad, rightEdge)
                rawMap \
                    = self.downsampledConvolutionMap[system.ypos,
                                                     leftMargin:rightMargin]
                barLineMap = _filtfilt(self.coeffs[0], self.coeffs[1], rawMap)
                smallPeaks = _peaks(barLineMap, self.minBarWidth * self.DPI)
                newPeaks = reshape(barLineMap[smallPeaks],
                                   (len(barLineMap[smallPeaks]), 1))
                codebook = cluster.vq.kmeans(newPeaks, 3) 
                codebook = reshape(codebook[0][argsort(codebook[0], 0)], (3, 1))
                newMap = reshape(barLineMap, (len(barLineMap), 1))
                clusters = cluster.vq.vq(newMap, codebook)
                barWidth = 2 * self.minBarWidth
                while 1:
                    metaPeaks = array(_peaks(barLineMap, barWidth * self.DPI))
                    barLines \
                        = metaPeaks[clusters[0][metaPeaks] != 0] + leftMargin
                    if len(barLines) <= self.maxBarLines \
                           and (len(barLines) < 3
                                or (barLines[1] - barLines[0]
                                    > barLines[2] - barLines[1])):
                        break
                    barWidth += 1.0 / 6.0
                barLines = list(barLines)
#                 # Fix the problem with key signatures.
#                 if len(barLines) >= 3 \
#                     and barLines[1] - barLines[0] \
#                          < barLines[2] - barLines[1]:
#                     del barLines[1]
                barLineGroups.append((system, barLines))
            except:
                print "BarLine exception:", sys.exc_info()[1]
        if saveIntermediates:
            file = open(self.downsampledBarLinesFilename, 'w')
            pickle.dump(barLineGroups, file)
            file.close()
        return barLineGroups

    def _getBars(self, image, barLineGroups):
        rightEdge = image.shape[1] - 1
        bars = list()
        for system, barLines in barLineGroups:
            systemSize = system.systemrect[1] - system.systemrect[3]
            vpad = int(round(0.5 * systemSize))
            for i in range(1, len(barLines)):
                bar = image[system.systemrect[3]-vpad
                            :system.systemrect[1]+vpad,
                            max(barLines[i-1]-self.pad, 0)
                            :min(barLines[i]+self.pad, rightEdge)]
                if prod(bar.shape) > 0:
                    bars.append(bar)
        return bars

    def _saveBars(self, bars, directory):
        for i in range(len(bars)):
            barString = "output" + ('%(i)03d' % {'i': i + 1}) + ".jpg"
            misc.pilutil.imsave(os.path.join(directory, barString), bars[i])

    def getBars(self):
        if not os.path.exists(self.barsDirectory):
            os.mkdir(self.barsDirectory)
        image = misc.pilutil.fromimage(self.original)
        barLineGroups = self.barLines
        bars = self._getBars(image, barLineGroups)
        if saveIntermediates:
            self._saveBars(bars, self.barsDirectory)
        return bars

    def getDownsampledBars(self):
        if not os.path.exists(self.downsampledBarsDirectory):
            os.mkdir(self.downsampledBarsDirectory)
        image = self.downsampled
        barLineGroups = self.downsampledBarLines
        bars = self._getBars(image, barLineGroups)
        if saveIntermediates:
            self._saveBars(bars, self.downsampledBarsDirectory)
        return bars

    def writeBarLines(self):
        file = open(self.outputFilename, 'w')
        tildeFlag = False
        for system, barLines in self.barLines:
            if tildeFlag: file.write('~\n')
            tildeFlag = True
            for barLine in barLines:
                file.write(str(barLine) + ' '
                           + str(system.systemrect[3]) + ' '
                           + str(barLine) + ' '
                           + str(system.systemrect[1]) + '\n')
        file.close()

    original = property(getOriginal, doc='original image')
    staves = property(getStaves, doc='staff locations')
    downsampledStaves = property(getDownsampledStaves,

                                 doc='downsampled staff locations')
    downsampled = property(getDownsampled,
                           doc='downsampled greyscale image (72 dpi)')
    downsampledKernel = property(getDownsampledKernel,
                                 doc='downsampled kernel')
    downsampledConvolutionMap \
        = property(getDownsampledConvolutionMap,
                   doc='convolution after downsampling')
    systems = property(getSystems, doc='system locations')
    downsampledSystems = property(getDownsampledSystems,
                                  doc='system locations after downsampling')
    barLines = property(getBarLines, doc='list of system-barLine pairs')
    downsampledBarLines \
        = property(getDownsampledBarLines,
                   doc='list of downsampled system-barLine pairs')
    bars = property(getBars, doc='bar images')
    downsampledBars = property(getDownsampledBars,
                                  doc='downsampled bar images')

        
if __name__ == "__main__":

    def usage():
        print __doc__

    try:
        opts, args = getopt.getopt(sys.argv[1:], "hio:r:s")
    except getopt.GetoptError:
        usage()
        sys.exit(2)
    if len(args) == 0:
        usage()
        sys.exit(2)
    saveIntermediates = False
    outputRoot = os.getcwd()
    inputDPI = 400
    singleStaves = False
    for opt, arg in opts:
        if opt == '-h':
            usage()
            sys.exit()
        elif opt == '-i':
            saveIntermediates = True
        elif opt == '-o':
            outputRoot = arg
        elif opt == '-r':
            inputDPI = float(arg)
        elif opt == '-s':
            singleStaves = True
    context = BarlinerContext(outputRoot, saveIntermediates)
    barliners = [Barliner(context, inputDPI, singleStaves, arg)
                 for arg in args]
    for barliner in barliners:
        barliner.writeBarLines()
