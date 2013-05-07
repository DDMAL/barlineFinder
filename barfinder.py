from gamera.core import *
from gamera.toolkits import musicstaves, lyric_extraction, border_removal
from gamera.classify import BoundingBoxGroupingFunction, ShapedGroupingFunction
from gamera import classify
from gamera import knn
import PIL, os
import argparse

from meicreate import BarlineDataConverter
from pymei import MeiElement
import re
from pyparsing import nestedExpr
import sys
import collections
import sets

'''
Finds barlines in an image and outputs MEI.

usage:
python barfinder.py -g 'staffgrouphint' image_path mei_path
python barfinder.py -g '(2|)x2 (4(2|))' images/C_07a_ED-Kl_1_A-Wn_SHWeber90_S_009.tiff mei/C_07a_ED-Kl_1_A-Wn_SHWeber90_S_009.mei
'''

# set up command line argument structure
parser = argparse.ArgumentParser(description='Perform barline detection on an image and output the MEI.')
parser.add_argument('-g', '--staffgroups', help='staffgroups')
parser.add_argument('filein', help='input file (.tiff)')
parser.add_argument('fileout', help='output file (.mei)')
parser.add_argument('-v', '--verbose', help='increase output verbosity', action='store_true')
parser.add_argument('-nb', '--noborderremove', help='do not remove borders automatically', action='store_true')
parser.add_argument('-nr', '--norotation', help='do not automatically rotate', action='store_true')

class StaffGroupMismatch(Exception):
    '''
    Custom exception that is raised when the number of staves entered
    by the user does not equal that found by the staff finding algorithm
    '''

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)

class BarlineFinder:

    def __init__(self, ar_thresh=0.1, v_thresh=0.66, verbose=False):
        self.ar_thresh = ar_thresh
        self.v_thresh = v_thresh
        self.verbose = verbose

    def _border_removal(self, image):
        """
        Calculates and masks the image border, returns a new image
        """
        mask_border = image.border_removal(3, 5, 5, 0.8, 6.0, 0.8, 6.0, 0.25, 15, 23, 75, 45, 15)
        masked_image = image.mask(mask_border)
        return masked_image

    def _staffline_removal(self, image):
        """
        """
        i = musicstaves.MusicStaves_rl_roach_tatem(image, 0, 0)
        i.remove_staves(u'all', 5)
        return i.image

    def _despeckle(self, image, despeckle_value):
        """
        """
        return image.despeckle(despeckle_value)

    def _most_frequent_run_filter(self, image, mfr, despeckle_value):
        """
        """
        filtered_image = image.image_copy()
        filtered_image.filter_short_runs(mfr + 5, 'black') # most frequent run plus 1 pixel
        filtered_image.despeckle(despeckle_value)
        return filtered_image

    def _ccs(self, proc_image):
        """
        Performs connected component analysis
        """
        ccs = proc_image.cc_analysis()
        return ccs

    def _staff_line_position(self, image, image_dpi):
        """Finds the staff line position, but also corrects the output
        of the Miyao staff finder algorithm by connecting candidate
        sub-staves according to their position in the score, trying
        to glue related staves.

        Returns a vector with the vertices for each staff with the form 
        [(staff_number, x1, y1, x2, y2)], starting from number 1
        """
        sc_position = [] # staff candidate
        stf_position = []
        
        try:
            # using miyao as backup
            if self.verbose:
                print 'MIYAO'
            stf_instance = musicstaves.StaffFinder_miyao(image, 0, 0)
            stf_instance.find_staves(5, 20, 0.8, -1) # 5 lines
            polygon = stf_instance.get_polygon()
            for i, p in enumerate(polygon):
                ul = p[0].vertices[0]
                ur = p[0].vertices[-1]
                ll = p[len(p)-1].vertices[0]
                lr = p[len(p)-1].vertices[-1]

                x1 = ul.x
                y1 = ul.y
                x2 = lr.x
                y2 = lr.y
                sc_position.append([i + 1, x1, y1, x2, y2])

        except:
            # using dalitz first
            stf_instance = musicstaves.StaffFinder_dalitz(image, 0, 0)
            stf_instance.find_staves(5, 3, 60, 25, True, True, 0) # 5 lines
            skeleton = stf_instance.get_skeleton()
            for i, p in enumerate(skeleton):
                
                x1 = p[0].left_x
                x2 = x1 + len(p[0].y_list)

                y_list = p[0].y_list

                if y_list[0] > y_list[-1]:
                    y_list_last = [y.y_list[-1] for y in p]
                    y1 = min(y_list_last)
                    y_list_first = [y.y_list[0] for y in p]
                    y2 = max(y_list_first)

                else:
                    y_list_first = [y.y_list[0] for y in p]
                    y1 = min(y_list_first)
                    y_list_last = [y.y_list[-1] for y in p]
                    y2 = max(y_list_last)
                sc_position.append([i + 1, x1, y1, x2, y2])
            if self.verbose:
                print 'DALITZ'            

        # Glueing the output of the Miyao staff finder
        stf_position.append((sc_position[0]))
        j = 1
        for k, sc in enumerate(sc_position[1:]):
            x1 = stf_position[-1][1]
            y1 = stf_position[-1][2]
            x2 = stf_position[-1][3]
            y2 = stf_position[-1][4]
            mid_y = (sc[2]+sc[4])/2

            # Checks if a staff candidate lies in the same y-range that the previous one
            if y2 > mid_y > y1:
                # If the bounding box of the staff candidate upper left x-value is larger than 
                # the previous bounding box, and also if this value is larger than the previous 
                # difference:
                if sc[1] >= x1 and sc[1] - x1 >= x2 - x1:
                    stf_position.pop()
                    stf_position.append([j, x1, y1, sc[3], sc[4]])

                elif sc[1] < x1:
                    stf_position.pop()
                    stf_position.append([j, sc[1], sc[2], x2, y2])
            else:
                j += 1
                stf_position.append([j, sc[1], sc[2], sc[3], sc[4]])

        return stf_position

    def _system_position_parser(self, stf_position):
        """
        Returns the position of the systems
        """
        system_bb = [] # system_staff_position
        system_bb.append(stf_position[0])
        for sp in stf_position[1:]:
            if sp[5] == system_bb[-1][5]:
                if sp[1] < system_bb[-1][1]:
                    system_bb[-1][1] = sp[1]
                if sp[2] < system_bb[-1][2]:
                    system_bb[-1][2] = sp[2]
                if sp[3] > system_bb[-1][3]:
                    system_bb[-1][3] = sp[3]
                if sp[4] > system_bb[-1][4]:
                    system_bb[-1][4] = sp[4]
            else:
                system_bb.append(sp)
        return system_bb

    def _bar_candidate_check(self, bar_candidates, stf_position, system, image_dpi):
        """
        Several methods to discard and/or validate bar candidates:

        1) Checks if the candidate bars lie within the upper and lower 
        boundaries of each staff. 

        2) Checks if bar candidate upper o lower position lies within a stf_position

        3) Creates a barline at the beginning of each staff according 
        to the staff position by the Miyao staff finder.

        Returns a vector in the form: [[gameracore.Image, staff_no]]

        PARAMETERS
        ----------
        ar_thresh (Float): threshold parameter for aspect ratio of bar candidates
        v_thresh (Float): threshold parameter for the percentage of the staff height for bar candidates
                          to be within the system bounding box (y dimension)
        """

        checked_bars = []
        stf_height = sum([i[4]-i[2] for i in stf_position])/len(stf_position)
        system_bb = self._system_position_parser(stf_position)    
        no_sys =  len(system_bb) 

        if self.verbose:
            print 'STF_HEIGHT:{0}'.format(stf_height)

        def __within_bb_check(bc, bb):
            """
            Checks if a bar_candidate is inside a bounding_box (system or staff)
            """
            bc_mid_x = bc.offset_x + int((bc.ncols - 1) / 2)
            bc_mid_y = bc.offset_y + int((bc.nrows - 1) / 2)
            bb_x1, bb_x2 = bb[1], bb[3]
            bb_y1, bb_y2 = bb[2], bb[4]
            # print 'x1:{0}, y1:{1}, x2:{2}, y2:{3}, x_mid:{4}, y_mid:{5}'.format(bb_x1, bb_y1, bb_x2, bb_y2, bc_mid_x, bc_mid_y)

            if bc_mid_x > bb_x1 and bc_mid_x < bb_x2 and bc_mid_y > bb_y1 and bc_mid_y < bb_y2:
                return bb

        def __bar_candidate_grouping(ungrouped_bars):
            """
            Groups bar candidates
            """
            for bar in ungrouped_bars:
                bar.classify_heuristic('_group._part.bc')

            cknn = knn.kNNInteractive()
            cknn.set_glyphs(ungrouped_bars)
            grouped_bars = cknn.group_and_update_list_automatic(ungrouped_bars, \
                        max_parts_per_group = 10, \
                        grouping_function = BoundingBoxGroupingFunction(5000)) # Threshold distance in pixels between bounding boxes 
            
            if len(grouped_bars) < 1:
                grouped_bars.append(bar)
            return grouped_bars

        # 1. filter by aspect ratio
        bar_candidates = [bc for bc in bar_candidates if bc.aspect_ratio()[0] <= self.ar_thresh]# and bc.ncols <=15]
        if not len(bar_candidates):
            # if all candidates have been filtered, no need to filter more
            return []

        # aspect_ratio = [bc.aspect_ratio() for bc in bar_candidates]
        # print aspect_ratio

        # 2. Discard bar_candidates outside of all system_bb(filtering by middle position)
        filt_bar_candidates = []
        bc_av_width = 0
        for bc in bar_candidates:
            for s in system_bb:
                bb = __within_bb_check(bc, s)
                if bb:
                    filt_bar_candidates.append([bc, bb[5]])
                    bc_av_width += bc.ncols
                    break
        
        if not len(filt_bar_candidates):
            # if all candidates have been filtered, no need to filter more
            return []

        # Calculate the average width of bar candidates
        bc_av_width = bc_av_width/len(filt_bar_candidates) 

        # print 'filt_bar_candidates:{0}'.format(filt_bar_candidates)
        
        # group bar candidates by system which they belong
        sys_bars = []
        for i in xrange(no_sys):
            sys_bars.append([x for x in filt_bar_candidates if x[1] == i+1])

        for sys_bar_idx, sys_bar in enumerate(sys_bars):
            bars = []
            system_height = abs(system_bb[sys_bar_idx][4]-system_bb[sys_bar_idx][2])

            factor = 4 # vertical tolerance for finding vertical candidates
            brok_cand_list = []
            for s_ind, s in enumerate(sys_bar): #each bar candidate within the same system

                brok_cand = [x[0] for x in sys_bar if \
                        (s[0].offset_x > (x[0].offset_x - factor * bc_av_width) and \
                         s[0].offset_x < (x[0].offset_x + factor * bc_av_width))] # This should be dependent on the number of staves per system

                if not brok_cand in brok_cand_list: # if it is not already in the list of broken bar candidates
                    brok_cand_list.append(brok_cand)

                    if len(brok_cand) > 1:   
                        grouped_bars = __bar_candidate_grouping(brok_cand)
                        while len(grouped_bars) > 1:
                            grouped_bars = __bar_candidate_grouping(grouped_bars) # run until all candidates have been glued
                        bars.append(grouped_bars[0])
                    else:
                        bars.append(s[0])

            for bc in bars:
                checked_bars.append((bc, sys_bar_idx+1))

        # filtering bar candidates that are outside a y-range of tolerance
        for cb_idx in range(len(checked_bars)-1, -1, -1):
            cb = checked_bars[cb_idx]
            bc_y1 = cb[0].offset_y
            bc_y2 = cb[0].offset_y + cb[0].nrows
            bb_y1 = system_bb[cb[1]-1][2]
            bb_y2 = system_bb[cb[1]-1][4]
            tolerance = self.v_thresh * stf_height #tolerance dependent on 

            if abs(bc_y1 - bb_y1) > tolerance or abs(bc_y2 - bb_y2) > tolerance:
                del checked_bars[cb_idx]

        if not len(checked_bars):
            # if all candidates have been filtered, no need to filter more
            return []

        # comparing first and last bar candidate with staffFinder output
        # converting the barline candidate structure into a different one
        # where bar candidates are ordered according to the system they belong:
        # system_bars[sys_no][bar_no]
        system_bars = []
        for i, cb in enumerate(checked_bars):
            system_no = int(cb[1])
            bar_image = cb[0]
            try:
                system_bars[system_no-1].append(bar_image)
            except IndexError:
                system_bars.append([bar_image])

        # sort all system bar candidates by x-position
        system_bars = [sorted(sb, key = lambda element: element.offset_x) for sb in system_bars]

        for idx, sb in enumerate(system_bars):
            # first and last bars
            fb_x, lb_x = sb[0].offset_x, sb[-1].offset_x 
            bb_x1, bb_x2 = system_bb[idx][1], system_bb[idx][3]
            bb_y1, bb_y2 = system_bb[idx][2], system_bb[idx][4]
            tolerance = 1 * stf_height
            system_height = abs(system_bb[sys_bar_idx][4]-system_bb[sys_bar_idx][2])

            if abs(fb_x - bb_x1) > tolerance:
                # create a new blank image for a manually created bar candidate from the stafffinder output
                new_bc = Image(Point (bb_x1, bb_y1), Point(bb_x1 + bc_av_width, bb_y1 + system_height))
                sb.insert(0, new_bc)

            if abs(lb_x - bb_x2) > tolerance:
                # create a new blank image for a manually created bar candidate from the stafffinder output
                new_bc = Image(Point (bb_x2, bb_y2), Point(bb_x2 + bc_av_width, bb_y2 + system_height))
                sb.append(new_bc)

            # filters bar candidates that are close together by x
            tolerance = 2 * stf_height # maximum horizontal is given the maximum amount of alterations
            for jdx in range(len(sb) - 1, 0, -1):
                if abs(sb[jdx - 1].offset_x - sb[jdx].offset_x) < tolerance:
                    del sb[jdx]

        checked_bars = []
        for idx, sb in enumerate(system_bars):
            for bar in sb:
                checked_bars.append((bar, idx+1))

        if self.verbose:
            print 'Checked bars:{0}'.format(checked_bars)

        return checked_bars

    def _staff_number_assign(self, bars_bb, staff_bb):
        """
        Assigns staff number to all bars
        """

        numbered_bars = []
        for bar in bars_bb:
            for staff_idx, staff in enumerate(staff_bb):
                staff_check = self._within_bb_checker(bar, staff)
                if staff_check == True:
                    numbered_bars.append((staff[0], bar[1], staff[2], bar[3], staff[4]))
        return numbered_bars


    def _within_bb_checker(self, bar_bb, staff_bb):
        """
        Checks if a bar_candidate is inside a bounding_box (system or staff)
        """
        x_bar_range = (bar_bb[1], bar_bb[3])
        y_bar_range = (bar_bb[2], bar_bb[4])

        x_staff_range = (staff_bb[1], staff_bb[3])
        y_staff_range = (staff_bb[2], staff_bb[4])

        for y in xrange(y_bar_range[0], y_bar_range[1]+1):
            if y_staff_range[0] < y < y_staff_range[1]:
                return True


    def _bar_sorting(self, bar_vector):
        """
        Sorts a set of bars according to their staff number and x-position. Input vector should be:
        [staff_no, ux, uy, lx, ly]
        """
        checked_bars = sorted(bar_vector, key = lambda element: (element[0], element[1]))
        # lg.debug(checked_bars)
        return checked_bars

    def _system_structure_parser(self, system_input):
        """
        Parses the structure of the system according to the user input
        """
        system = system_input.split(',')
        output = []
        for i, s in enumerate(system):
            for j in range(int(s)):
                output.append(i+1)
        return output
    
    def _parse_staff_hint(self, sg_hint):
        # parse staff group hint to generate staff group
        sg_hint = sg_hint.split(" ")
        systems = []
        for s in sg_hint:
            parser = nestedExpr()
            sg_list = parser.parseString(s).asList()[0]
            staff_grp, n = self._create_staff_group(sg_list, MeiElement('staffGrp'), 0)

            # parse repeating staff groups (systems)
            num_sb = 1
            match = re.search('(?<=x)(\d+)$', s)
            if match is not None:
                # there are multiple systems of this staff grouping
                num_sb = int(match.group(0))
            
            for i in range(num_sb):
                systems.append(staff_grp)

        return systems

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
                # check for barthrough character
                if sg_list[0][-1] == '|':
                    # the barlines go through all the staves in the staff group
                    staff_grp.addAttribute('barthru', 'true')
                    # remove the barthrough character, should now only be an integer
                    sg_list[0] = sg_list[0][:-1]

                n_staff_defs = int(sg_list[0])
                # get current staffDef number
                for i in range(n_staff_defs):
                    staff_def = MeiElement('staffDef')
                    staff_def.addAttribute('n', str(n+i+1))
                    staff_grp.addChild(staff_def)
                n += n_staff_defs

            return self._create_staff_group(sg_list[1:], staff_grp, n)

    def _highlight(self, image, ccs_bars):
        RGB_image = image.to_rgb()
        for c in ccs_bars:
            RGB_image.highlight(c[0], RGBPixel(255, 0, 0))
        return RGB_image

    # def _filter_close_bar_bb(self, sorted_bars, staff_bb, image_dpi):
    #     # print 'A', image_dpi
    #     for sb in sorted_bars[:]:
    #         print sb
    #     for st in staff_bb[:]:
    #         print st

        filtered_bars = sorted_bars
        return filtered_bars

    def process_file(self, input_file, sg_hint, noborderremove=False, norotation=False):
        '''
        Find measures in the given input file.

        PARAMETERS
        ----------
        sg_hint: staff group hint inputted manually by the user
        noborderremove: flag to specify whether the automatic border removal algorithm should be used
        norotation: flag to specify whether the automatic rotation algorithm should be used
        '''

        image = load_image(input_file)

        # since they want to be able to disclude this step from the workflow on the command line
        if not noborderremove:
            #Applies a mask. Greyscale image needed
            if image.pixel_type_name != 'GreyScale':
                image = image.to_greyscale()
            image = self._border_removal(image)

        # Binarizes image
        image = image.to_onebit()

        # since they want to be able to disclude this step from the workflow
        if not norotation:
            # Auto-rotates an image
            image = image.correct_rotation(0)

        # image = image.dilate()
        # save the image that barline candidates are calculated from
        # the MEI will reference this file
        image_path = os.path.splitext(input_file.split('/')[-1])[0] + '_preprocessed.tiff'
        image.save_tiff(image_path)
        image_width = image.width
        image_height = image.height

        # use PIL to get image resolution in the x dimension
        # because it is more reliable than gamera
        pil_image = PIL.Image.open(input_file)
        image_dpi = pil_image.info['dpi'][0]
        if image_dpi == 0:
            # set a default image dpi of 72
            if self.verbose:
                print "Manually setting image dpi to 72"
            image_dpi = 72

        if self.verbose:
            print 'DPI:{0}'.format(image_dpi)

        # parse the staff group hint into a list of staffGrps---one for each system
        # [staffGrps, ...]
        system_staff_groups = self._parse_staff_hint(sg_hint)

        barfinder_sg_hint = ", ".join([str(len(sg.getDescendantsByName('staffDef'))) for sg in system_staff_groups])
        system = self._system_structure_parser(barfinder_sg_hint)

        if self.verbose:
            print "SG HINT:{0}".format(sg_hint) #GVM

        # Returns the vertices for each staff and its number
        stf_position = self._staff_line_position(image, image_dpi)
        #print stf_position
        if len(stf_position) != len(system):
            raise StaffGroupMismatch('Number of recognized staves is different to the one entered by the user')

        # Appends the proper system number according to the user input
        for i, s in enumerate(stf_position):
            stf_position[i].append(system[i])

        staff_bb = []
        # Saving staff bounding boxes
        for st in stf_position:
            staff_bb.append([st[0], st[1], st[2], st[3], st[4]])
        # print stf_position, '\n' #GVM
        # print staff_bb, '\n' #GVM
        # Staff-line removal
        mfr = image.most_frequent_run('black', 'vertical')
        # despeckle value equation for mfr: [1,10], [2,50], [3,100]
        despeckle_value = int(45 * mfr - 36.67)
        if self.verbose:
            print 'MFR:{0}, DV:{1}'.format(mfr, despeckle_value)
        no_staff_image = self._staffline_removal(image)
        self._despeckle(no_staff_image, despeckle_value)
        no_staff_image.save_tiff(os.path.splitext(input_file.split('/')[-1])[0] + '_no_stafflines.tiff')

        # Filters short-runs
        filtered_image = self._most_frequent_run_filter(no_staff_image, mfr, despeckle_value)    # most_frequent_run
        filtered_image.save_tiff(os.path.splitext(input_file.split('/')[-1])[0] + '_no_mfr.tiff')

        # cc's and highlighs no staff and short runs filtered image and writes txt file with candidate bars
        ccs_bars = self._ccs(filtered_image)


        # print ccs_bars
        image_ccs_mfr = self._highlight(filtered_image, [[c] for c in ccs_bars if c.aspect_ratio()[0] <= 0.05])
        image_ccs_mfr.save_tiff(os.path.splitext(input_file.split('/')[-1])[0] + '_ccs_mfr.tiff')

        checked_bars = self._bar_candidate_check(ccs_bars, stf_position, system, image_dpi)

        RGB_image = self._highlight(image, checked_bars)
        output_path = os.path.splitext(input_file.split('/')[-1])[0] + '_candidates.tiff'
        RGB_image.save_tiff(output_path) #GVM

        bar_list = []
        for c in checked_bars:
            bar_list.append([c[1], c[0].offset_x, c[0].offset_y, c[0].offset_x+c[0].ncols-1, c[0].offset_y+c[0].nrows-1])

        sorted_bars = self._bar_sorting(bar_list)
        # for sb in sorted_bars: print sb

        numbered_bars = self._staff_number_assign(sorted_bars, staff_bb)
        
        # for nb in numbered_bars: print 'NUMBERED BARS:{0}'.format(nb)
        return staff_bb, numbered_bars, image_path, image_width, image_height, image_dpi

if __name__ == "__main__":
    init_gamera()

    # parse command line arguments
    args = parser.parse_args()
    input_file = args.filein
    
    if not os.path.exists(input_file):
        raise ValueError('The input file does not exist')

    output_file = args.fileout
    sg_hint = args.staffgroups
    verbose = args.verbose
    noborderremove = args.noborderremove
    norotation = args.norotation

    # internal parameters for filtering barline candidates
    ar_thresh = 0.25
    v_thresh = 0.66

    bar_finder = BarlineFinder(ar_thresh, v_thresh, verbose)
    staff_bb, bar_bb, image_path, image_width, image_height, image_dpi = bar_finder.process_file(input_file, sg_hint, noborderremove, norotation)
    # print '\nSTAFF_BB:{0}\n\nBAR_BB:{1}'.format(staff_bb, bar_bb)
    bar_converter = BarlineDataConverter(staff_bb, bar_bb, verbose)
    bar_converter.bardata_to_mei(sg_hint, image_path, image_width, image_height, image_dpi)
    bar_converter.output_mei(output_file)
