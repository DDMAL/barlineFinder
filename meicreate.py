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

Sample usage:
python meicreate.py -b ../Results/N_10_D_kl_Baermann_GA_cl_002_bar_position_1.txt -s ../Results/N_10_D_kl_Baermann_GA_cl_002_staff_vertices.txt -f detmoldbars.mei -g '(1)' -v    
"""

import argparse
from pyparsing import nestedExpr
import os

from pymei import MeiDocument, MeiElement, XmlExport

# set up command line argument structure
parser = argparse.ArgumentParser(description='Convert text file of OMR barline data to mei.')
parser.add_argument('-b', '--barfilein', help='barline data input file')
parser.add_argument('-s', '--stafffilein', help='staff data input file')
parser.add_argument('-g', '--staffgroups', help='staffgroups')
parser.add_argument('-f', '--fileout', help='output file')
parser.add_argument('-v', '--verbose', help='increase output verbosity', action='store_true')

class BarlineDataConverter:
    '''
    Convert the output of the barline detection algorithm
    to MEI.
    '''

    def __init__(self, bar_input_path, staff_input_path, verbose):
        '''
        Initialize the converter
        '''

        self.bar_input_path = bar_input_path
        self.staff_input_path = staff_input_path
        self.verbose = verbose

    def bardata_to_mei(self, sg_hint):
        '''
        Perform the data conversion to mei
        '''

        self.meidoc = MeiDocument()
        mei = MeiElement('mei')
        self.meidoc.setRootElement(mei)

        ###########################
        #         MetaData        #
        ###########################
        mei_head = MeiElement('meiHead')
        mei.addChild(mei_head)

        ###########################
        #           Body          #
        ###########################
        music = MeiElement('music')
        body = MeiElement('body')
        mdiv = MeiElement('mdiv')
        score = MeiElement('score')
        score_def = MeiElement('scoreDef')
        section = MeiElement('section')

        # physical location data
        facsimile = MeiElement('facsimile')
        surface = MeiElement('surface')

        # generate staff group
        parser = nestedExpr()
        sg_list = parser.parseString(sg_hint).asList()[0]
        staff_grp, n = self._create_staff_group(sg_list, MeiElement('staffGrp'), 0)
        if self.verbose:
            print "number of staves: %d" % n

        mei.addChild(music)
        music.addChild(facsimile)
        facsimile.addChild(surface)
        
        # get bounding box information of staves
        layout = MeiElement('layout')
        page = MeiElement('page')
        music.addChild(layout)
        layout.addChild(page)

        # this encoding will work for one-staff systems like in liber
        # TODO: find out how to attach facs data to an individual staff in a system
        with open(self.staff_input_path, 'r') as staff_output:
            for staff_bb in staff_output:
                # get bounding box of the staff
                staff_bb = staff_bb.split("\t")[1:]
                zone = self._create_zone(staff_bb[0], staff_bb[1], staff_bb[2], staff_bb[3])
                surface.addChild(zone)
                system = MeiElement('system')
                system.addAttribute('facs', zone.getId())
                page.addChild(system)
        
        music.addChild(body)
        body.addChild(mdiv)
        mdiv.addChild(score)
        score.addChild(score_def)
        score_def.addChild(staff_grp)
        score.addChild(section)

        staff_defs = staff_grp.getDescendantsByName('staffDef')
        system_refs = page.getChildrenByName('system')
        with open(self.bar_input_path, 'r') as bar_output:
            cur_staff = None
            cur_layer = None
            cur_staff_num = 0
            for i, barline in enumerate(bar_output):
                barline = barline.split("\t")

                staff_num = int(barline[0])
                if staff_num != cur_staff_num:
                    # a new staff or system
                    if cur_staff is None or staff_num % len(staff_defs) != 0:
                        # a new staff
                        cur_staff = MeiElement('staff')
                        cur_staff.addAttribute('n', str(staff_num % len(staff_defs) + 1))
                        cur_layer = MeiElement('layer')
                        cur_layer.addAttribute('n', '1')
                        if staff_num == 1:
                            sb = self._create_sb(system_refs, staff_num)
                            cur_layer.addChild(sb)

                        section.addChild(cur_staff)
                        cur_staff.addChild(cur_layer)
                    else:
                        # a new system break
                        sb = self._create_sb(system_refs, staff_num)
                        cur_layer.addChild(sb)

                cur_staff_num = staff_num
                        
                ulx = barline[1]
                uly = barline[2]
                lrx = barline[3]
                lry = barline[4]

                barline = MeiElement('barLine')
                zone = self._create_zone(ulx, uly, lrx, lry)
                surface.addChild(zone)
                barline.addAttribute('facs', zone.getId())
                cur_layer.addChild(barline)

            if self.verbose:
                print "%d barlines processed." % i

    def output_mei(self, output_path):
        '''
        Write the generated mei to disk
        '''

        # output mei file
        XmlExport.meiDocumentToFile(self.meidoc, output_path)

    def _create_staff_group(self, sg_list, staff_grp, n):
        '''
        Recursively create the staff group element from the parsed
        user input of the staff groupings
        '''
        if not sg_list:
            return staff_grp, n
        else:
            if type(sg_list[0]) is list:
                new_staff_grp, n = self._create_staff_group(sg_list[0], MeiElement('staffGrp'), n)
                staff_grp.addChild(new_staff_grp)
            else:
                n_staff_defs = int(sg_list[0])
                # get current staffDef number
                for i in range(n_staff_defs):
                    staff_def = MeiElement('staffDef')
                    staff_def.addAttribute('n', str(n+i+1))
                    staff_grp.addChild(staff_def)
                n += n_staff_defs

            return self._create_staff_group(sg_list[1:], staff_grp, n)

    def _create_sb(self, system_refs, staff_num):
        '''
        Create a system break element and attach it to a system reference
        '''

        sb = MeiElement('sb')
        sb.addAttribute('systemref', str(system_refs[staff_num-1].getId()))
        sb.addAttribute('n', str(staff_num))

        return sb

    def _create_zone(self, ulx, uly, lrx, lry):
        '''
        Create a zone element
        '''

        zone = MeiElement('zone')
        zone.addAttribute('ulx', ulx)
        zone.addAttribute('uly', uly)
        zone.addAttribute('lrx', lrx)
        zone.addAttribute('lry', lry)

        return zone

if __name__ == "__main__":
    # parse command line arguments
    args = parser.parse_args()

    bar_input_path = args.barfilein
    staff_input_path = args.stafffilein
    if not os.path.exists(bar_input_path) or not os.path.exists(staff_input_path):
        raise ValueError('The input file does not exist')

    output_path = args.fileout
    sg_hint = args.staffgroups
    verbose = args.verbose
    bar_converter = BarlineDataConverter(bar_input_path, staff_input_path, verbose)
    bar_converter.bardata_to_mei(sg_hint)
    bar_converter.output_mei(output_path)
