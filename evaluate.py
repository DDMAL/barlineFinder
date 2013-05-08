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
from PIL import Image

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

    def __init__(self, dataroot, interfiles=False, verbose=False):
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
        self._interfiles = interfiles

        init_gamera()

    def evaluate(self, ar_thresh, v_thresh, bb_padding_in=0.05, log=None):
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
            logging.basicConfig(format='%(message)s', filename=log, filemode='a', level=logging.DEBUG)
            logging.info("Beginning experiment.")
            logging.info("Parameters: ar_thresh=%.3f, v_thresh=%.3f, bb_padding_in=%.3f" % (ar_thresh, v_thresh, bb_padding_in))
            if self.verbose:
                print "Beginning experiment."
                print "Parameters: ar_thresh=%.3f, v_thresh=%.3f, bb_padding_in=%.3f" % (ar_thresh, v_thresh, bb_padding_in)

        precision = []
        recall = []
        fmeasure = []

        '''
        process all image files. Assumes the directory structure is:
        > dataroot/1
        >> filename.tiff        (music score image)
        >> filename.mei         (ground-truth mei file)
        >> filename_ao.mei      (algorithm MEI output)
        >> filename.txt         (staff group hint)
        ...
        > dataroot/N
        >> filename.tiff        (music score image)
        >> filename.mei         (ground-truth mei file)
        >> filename_ao.mei      (algorithm MEI output)
        >> filename.txt         (staff group hint)
        '''
        num_errors = 0
        data_points = [d for d in os.listdir(self.datapath) if os.path.isdir(os.path.join(self.datapath, d))]
        for i, d in enumerate(data_points):
            data_point_path = os.path.join(self.datapath, d)

            if self.verbose:
                print "processing music score (%d/%d)" % (i+1, len(data_points))
            logging.info("processing music score (%d/%d)" % (i+1, len(data_points)))

            data_files = [os.path.join(data_point_path, f) for f in os.listdir(data_point_path)]
            image_path = [f for f in data_files if f.endswith('.tiff') and not f.endswith('_preprocessed.tiff')][0]
            sg_hint_file_path = [f for f in data_files if f.endswith('.txt')][0]
            gt_mei_path = [f for f in data_files if f.endswith('.mei') and not f.endswith('_ao.mei')][0]
            mei_path = [f for f in data_files if f.endswith('_%.3f_%.3f_ao.mei' % (ar_thresh, v_thresh))]
            filename = os.path.splitext(os.path.split(image_path)[1])[0]

            if len(mei_path):
                # the algorithm has already been run with the given parameters
                mei_path = mei_path[0]

                # still need the image dpi (in the x plane)
                image = Image.open(image_path)
                image_dpi = image.info['dpi'][0]
                if image_dpi == 0:
                    # set a default image dpi of 72
                    logging.info('[WARNING] manually setting img resolution to 72')
                    print '[WARNING] manually setting img resolution to 72'
                    image_dpi = 72
            else:
                # the algorithm has not been run already, run it
                mei_path = os.path.join(data_point_path, '%s_%.3f_%.3f_ao.mei' % (filename, ar_thresh, v_thresh))

                # get staff group hint
                sg_hint = self._get_sg_hint(sg_hint_file_path)

                # run the measure finding algorithm and write the output to mei
                try:
                    bar_finder = BarlineFinder(ar_thresh, v_thresh, self._interfiles, self.verbose)
                    noborderremove = True
                    norotation = False
                    staff_bb, bar_bb, _, image_width, image_height, image_dpi = bar_finder.process_file(image_path, sg_hint, noborderremove, norotation)

                    bar_converter = BarlineDataConverter(staff_bb, bar_bb, self.verbose)
                    bar_converter.bardata_to_mei(sg_hint, image_path, image_width, image_height, image_dpi)
                    bar_converter.output_mei(mei_path)
                except:
                    # there was an error with the measure finding algorithm
                    num_errors += 1
                    continue                

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

        logging.info("Done experiment.")
        logging.info("Number of errors: %d" % num_errors)
        if self.verbose:
            print "Done experiment."
            print "Number of errors: %d" % num_errors

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
            for i in range(len(gt_bb)-1,-1,-1):
                # check if it is nearby a ground-truth measure bounding box
                if (abs(abb['ulx']-gt_bb[i]['ulx']) <= bb_padding_px and 
                    abs(abb['uly']-gt_bb[i]['uly']) <= bb_padding_px and 
                    abs(abb['lrx']-gt_bb[i]['lrx']) <= bb_padding_px and
                    abs(abb['lry']-gt_bb[i]['lry']) <= bb_padding_px):
                    r += 1
                    del gt_bb[i]
                    break

        if num_alg_measures > 0:
            p = r / num_alg_measures
        else:
            if self.verbose:
                print '[WARNING]: no algorithm output measures found'
            p = 0
        
        if num_gt_measures > 0:
            r /= num_gt_measures
        else:
            if self.verbose:
                print '[WARNING]: no ground-truth measures found'
            r = 1

        f = calc_fmeasure(p,r)

        return p, r, f

if __name__ == "__main__":
    # parse command line arguments
    args = parser.parse_args()
    dataroot = args.dataroot
    verbose = args.verbose

    gen_interfiles = False
    emf = EvaluateMeasureFinder(dataroot, gen_interfiles, verbose)
    bb_padding_in = 0.5

    # create parameter matrix
    param_matrix_size = 3
    ar_min_max = (0.08125, 0.19375)
    v_min_max = (0.325, 0.775)
    ar_threshes = np.linspace(ar_min_max[0], ar_min_max[1], param_matrix_size)
    v_threshes = np.linspace(v_min_max[0], v_min_max[1], param_matrix_size)

    for ar_thresh in ar_threshes:
        for v_thresh in v_threshes:
            emf.evaluate(ar_thresh, v_thresh, bb_padding_in, 'experimentlog.txt')
