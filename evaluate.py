"""
Copyright (c) 2013, Gregory Burlet
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:
    * Redistributions of source code must retain the above copyright
      notice, this list of conditions and the following disclaimer.
    * Redistributions in binary form must reproduce the above copyright
      notice, this list of conditions and the following disclaimer in the
      documentation and/or other materials provided with the distribution.
    * Neither the name of the <organization> nor the
      names of its contributors may be used to endorse or promote products
      derived from this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL <COPYRIGHT HOLDER> BE LIABLE FOR ANY
DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

Evaluates the implemented measure finding algorithm on a dataset of music scores.

Note: the barlineFinder package must be declared in your PYTHONPATH variable.

Sample usage:
python evaluate.py path/to/data -v
"""

from __future__ import division
from barlineFinder.barfinder import BarlineFinder
from barlineFinder.meicreate import BarlineDataConverter
from pymei import XmlImport, MeiDocument
from gamera.core import *
import os
import logging
import argparse
import numpy as np

# set up command line argument structure
parser = argparse.ArgumentParser(description='Perform experiment reporting performance of the measure finding algorithm.')
parser.add_argument('dataroot', help='path to the dataset')
parser.add_argument('-v', '--verbose', help='increase output verbosity', action='store_true')

def calc_fmeasure(precision, recall):
    '''
    Calculate f-measure with equal balance between precision and recall

    PARAMETERS
    ----------
    precision (float)
    recall (float)
    '''

    if precision + recall > 0:
        fmeasure = (2 * precision * recall) / (precision + recall)
    else:
        fmeasure = 0

    return fmeasure

class EvaluateMeasureFinder(object):

    def __init__(self, dataroot, verbose=False):
        '''
        Setup the experiment.

        PARAMETERS
        ----------
        dataroot (String): path to the dataset
        verbose (bool): stdout flag
        '''

        if os.path.isdir(dataroot):
            self.datapath = dataroot
        else:
            raise IOError

        self.verbose = verbose

        init_gamera()

    def evaluate(self, bb_padding_in=0.05, log=None):
        '''
        Evaluate the measure finding algorithm on the dataset using the metrics
        of precision, recall, and f-measure.

        PARAMETERS
        ----------
        bb_padding_in (float): measure bounding box padding (inches). 
                               Any measure within the padding is assumed correct.
        log (bool): create a log file of the results in the same directory
        '''

        if log:
            logging.basicConfig(format='%(message)s', filename=log, filemode='w', level=logging.DEBUG)
            logging.info("Beginning experiment.")
            if self.verbose:
                print "Beginning experiment."

        precision = []
        recall = []
        fmeasure = []

        '''
        process all image files. Assumes the directory structure is:
        > dataroot/1
        >> filename.tiff        (music score image)
        >> filename_gt.mei      (ground-truth mei file)
        >> filename.txt         (staff group hint)
        ...
        > dataroot/N
        >> filename.tiff        (music score image)
        >> filename_gt.mei      (ground-truth mei file)
        >> filename.txt         (staff group hint)
        '''
        num_images = 0
        cur_image = 1
        for dirpath, dirnames, filenames in os.walk(self.datapath):
            if len(dirnames):
                num_images = len(dirnames)

            filenames = [f for f in filenames if f.endswith(".tiff") and not f.endswith("._preprocessed.tiff")]
            for f in filenames:
                if self.verbose:
                    print "processing music score (%d/%d): %s" % (cur_image, num_images, f)
                logging.info("processing music score (%d/%d): %s" % (cur_image, num_images, f))

                filename, _ = os.path.splitext(f)
                image_path = os.path.join(dirpath, f)
                sg_hint_file_path = os.path.join(dirpath, filename+'.txt')
                gt_mei_path = os.path.join(dirpath, filename+'_gt.mei')
                mei_path = os.path.join(dirpath, filename+'.mei')

                # if the algorithm has not been run already, run it
                if not os.path.exists(mei_path):
                    # get staff group hint
                    sg_hint = self._get_sg_hint(sg_hint_file_path)

                    # run the measure finding algorithm and write the output to mei
                    bar_finder = BarlineFinder()
                    staff_bb, bar_bb, _, image_width, image_height, image_dpi = bar_finder.process_file(image_path, sg_hint)

                    bar_converter = BarlineDataConverter(staff_bb, bar_bb, verbose)
                    bar_converter.bardata_to_mei(sg_hint, image_path, image_width, image_height, image_dpi)
                    bar_converter.output_mei(mei_path)
                else:
                    # still need the image dpi
                    image = load_image(image_path)
                    if image.resolution != 0:
                        image_dpi = image.resolution
                    else:
                        # set a default image dpi of 72
                        image_dpi = 72

                # calculate number of pixels the padding is
                bb_padding_px = bb_padding_in * image_dpi

                p, r, f = self._evaluate_output(mei_path, gt_mei_path, bb_padding_px)
                if verbose:
                    print '\tprecision: %.2f\n\trecall: %.2f\n\tf-measure: %.2f' % (p, r, f)
                logging.info('\tprecision: %.2f\n\trecall: %.2f\n\tf-measure: %.2f' % (p, r, f))

                # keep track of global experiment results
                precision.append(p)
                recall.append(r)
                fmeasure.append(f)

                cur_image += 1

        logging.info("Done experiment.")
        if self.verbose:
            print "Done experiment."

        avg_precision = np.mean(precision)
        avg_recall = np.mean(recall)
        avg_fmeasure = np.mean(fmeasure)

        if self.verbose:
            print "\nAverage precision: %.2f\nAverage recall: %.2f\nAverage f-measure: %.2f" % (avg_precision, avg_recall, avg_fmeasure)
        logging.info("\nAverage precision: %.2f\nAverage recall: %.2f\nAverage f-measure: %.2f" % (avg_precision, avg_recall, avg_fmeasure))

    def _get_sg_hint(self, sg_hint_file_path):
        '''
        Retrieve the staff group hint for the measure finding algorithm
        '''
        with open(sg_hint_file_path, 'r') as f:
            sg_hint = f.readline().strip()

        return sg_hint

    def _evaluate_output(self, mei_path, gt_mei_path, bb_padding_px):
        '''
        Evaluate the output of the measure finding algorithm against the manual measure
        annotations.

        PARAMETERS
        ----------
        mei_path (String): path to mei document created by algorithm
        gt_mei_path (String): path to mei document created by annotator
        bb_padding_px (int): number of pixels to pad the ground-truth measure bounding boxes
        '''

        meidoc = XmlImport.documentFromFile(mei_path)
        gtmeidoc = XmlImport.documentFromFile(gt_mei_path)

        p = 0.0     # precision
        r = 0.0     # recall
        f = 0.0     # f-measure

        # get bounding boxes of ground-truth measures
        gt_measure_zones = gtmeidoc.getElementsByName('zone')
        gt_bb = [{
            'ulx': int(z.getAttribute('ulx').value),
            'uly': int(z.getAttribute('uly').value),
            'lrx': int(z.getAttribute('lrx').value), 
            'lry': int(z.getAttribute('lry').value)
        } for z in gt_measure_zones]
        num_gt_measures = len(gt_measure_zones)

        # get bounding boxes of algorithm measures
        alg_measure_zones = [meidoc.getElementById(m.getAttribute('facs').value[1:])
                            for m in meidoc.getElementsByName('measure') 
                            if m.hasAttribute('facs')]

        alg_bb = [{
            'ulx': int(z.getAttribute('ulx').value),
            'uly': int(z.getAttribute('uly').value),
            'lrx': int(z.getAttribute('lrx').value), 
            'lry': int(z.getAttribute('lry').value)
        } for z in alg_measure_zones]
        num_alg_measures = len(alg_bb)

        # compare each measure bounding box estimate to the ground truth
        # deleting after to ensure no double counting.
        for abb in alg_bb:
            for i, gbb in enumerate(gt_bb):
                # check if it is nearby a ground-truth measure bounding box
                if (abs(abb['ulx']-gbb['ulx']) <= bb_padding_px and 
                    abs(abb['uly']-gbb['uly']) <= bb_padding_px and 
                    abs(abb['lrx']-gbb['lrx']) <= bb_padding_px and
                    abs(abb['lry']-gbb['lry']) <= bb_padding_px):
                    r += 1
                    del gbb[i]
                    break

        p = r / num_alg_measures
        r /= num_gt_measures
        f = calc_fmeasure(p,r)

        return p, r, f

if __name__ == "__main__":
    # parse command line arguments
    args = parser.parse_args()
    dataroot = args.dataroot
    verbose = args.verbose

    emf = EvaluateMeasureFinder(dataroot, verbose)
    bb_padding_in = 0.05
    emf.evaluate(bb_padding_in, 'experimentlog.txt')
