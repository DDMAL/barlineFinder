"""
Copyright (c) 2012, Gregory Burlet
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

"""

import argparse
from pyparsing import nestedExpr
import os

from pymei import MeiDocument, MeiElement, XmlExport

# set up command line argument structure
parser = argparse.ArgumentParser(description='Convert text file of OMR barline data to mei.')
parser.add_argument('-fin', '--filein', help='input file')
parser.add_argument('-sgs', '--staffgroups', help='staffgroups')
parser.add_argument('-fout', '--fileout', help='output file')
parser.add_argument('-v', '--verbose', help='increase output verbosity', action='store_true')

def bardata_to_mei(input_path, staff_groups, output_path, verbose):
    meidoc = MeiDocument()
    mei = MeiElement('mei')
    meidoc.setRootElement(mei)

    ###########################
    #         MetaData        #
    ###########################
    mei_head = MeiElement('meihead')
    mei.addChild(mei_head)

    ###########################
    #           Body          #
    ###########################
    music = MeiElement('music')
    body = MeiElement('body')
    mdiv = MeiElement('mdiv')
    score = MeiElement('score')
    score_def = MeiElement('score_def')
    section = MeiElement('section')

    # physical location data
    facsimile = MeiElement('facsimile')
    surface = MeiElement('surface')

    # generate staff group
    parser = nestedExpr()
    sg_list = parser.parseString(staff_groups).asList()[0]
    staff_grp, n = _create_staff_group(sg_list, MeiElement('staffGrp'), 0)
    if verbose:
        print "number of staves: %d" % n

    mei.addChild(music)
    music.addChild(facsimile)
    facsimile.addChild(surface)
    music.addChild(body)
    body.addChild(mdiv)
    mdiv.addChild(score)
    score.addChild(score_def)
    score_def.addChild(staff_grp)
    score.addChild(section)

    with open(input_path, 'r') as bar_output:
        cur_staff = None
        cur_layer = None
        for i, barline in enumerate(bar_output):
            barline = barline.split("\t")

            staff_num = barline[0]
            if cur_staff is None or staff_num != cur_staff.getAttribute('n').value:
                # a new staff
                cur_staff = MeiElement('staff')
                cur_staff.addAttribute('n', staff_num)
                cur_layer = MeiElement('layer')
                cur_layer.addAttribute('n', '1')
                section.addChild(cur_staff)
                cur_staff.addChild(cur_layer)

            ulx = barline[1]
            uly = barline[2]
            lrx = barline[3]
            lry = barline[4]

            barline = MeiElement('barLine')
            zone = _create_zone(ulx, uly, lrx, lry)
            facsimile.addChild(zone)
            barline.addAttribute('facs', zone.getId())
            cur_layer.addChild(barline)

        if verbose:
            print "%d barlines processed." % i

    # output mei file
    XmlExport.meiDocumentToFile(meidoc, output_path)

def _create_staff_group(sg_list, staff_grp, n):
    if not sg_list:
        return staff_grp, n
    else:
        if type(sg_list[0]) is list:
            new_staff_grp, n = _create_staff_group(sg_list[0], MeiElement('staffGrp'), n)
            staff_grp.addChild(new_staff_grp)
        else:
            n_staff_defs = int(sg_list[0])
            # get current staffDef number
            for i in range(n_staff_defs):
                staff_def = MeiElement('staffDef')
                staff_def.addAttribute('n', str(n+i+1))
                staff_grp.addChild(staff_def)
            n += n_staff_defs

        return _create_staff_group(sg_list[1:], staff_grp, n)

def _create_zone(ulx, uly, lrx, lry):
    zone = MeiElement('zone')
    zone.addAttribute('ulx', ulx)
    zone.addAttribute('uly', uly)
    zone.addAttribute('lrx', lrx)
    zone.addAttribute('lry', lry)

    return zone

if __name__ == "__main__":
    # parse command line arguments
    args = parser.parse_args()

    input_path = args.filein
    if not os.path.exists(input_path):
        raise ValueError('The input file does not exist')

    output_path = args.fileout
    staff_groups = args.staffgroups
    verbose = args.verbose
    bardata_to_mei(input_path, staff_groups, output_path, verbose)
