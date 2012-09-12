# from pymei.Import import xmltomei
from gamera.core import *
from gamera.toolkits import musicstaves, lyric_extraction, border_removal
from gamera import classify
from gamera import knn
import PIL, os
from optparse import OptionParser
init_gamera()


import logging
lg = logging.getLogger('pitch_find')
f = logging.Formatter("%(levelname)s %(asctime)s On Line: %(lineno)d %(message)s")
h = logging.StreamHandler()
h.setFormatter(f)

lg.setLevel(logging.DEBUG)
lg.addHandler(h)



def border_removal(image):
    """
    Calculates and masks the image border, returns a new image
    """
    mask_border = image.border_removal(3, 5, 5, 0.8, 6.0, 0.8, 6.0, 0.25, 15, 23, 75, 45, 15)
    masked_image = image.mask(mask_border)
    return masked_image

def binarize(filepath):
    """
    """

    if input_image.pixel_type_name == 'GreyScale':
        binarized_image = input_image.abutaleb_threshold(0)
    elif input_image.pixel_type_name == 'RGB':
        binarized_image = i.djvu_threshold(0.2, 512, 64, 2)
    else:
        binarized_image = input_image
    return binarized_image


def staffline_removal(image):
    """
    """
    i = musicstaves.MusicStaves_rl_roach_tatem(image, 0, 0)
    i.remove_staves(u'all', 5)
    return i.image

def despeckle(image):
    """
    """
    return image.despeckle(100)

def most_frequent_run_filter(image, mfr):
    """
    """
    filtered_image = image.image_copy()
    filtered_image.filter_short_runs(mfr + 2, 'black') # most frequent run plus 1 pixel
    filtered_image.despeckle(100)
    return filtered_image

def ccs(proc_image):
    """
    Performs connected component analysis and filters 
    using a certain set of features.
    """
    ccs = proc_image.cc_analysis()
    ccs_bars = []
    for c in ccs:
            if c.aspect_ratio()[0] <= 0.20 and c.ncols <= 15: # try other features and/or values
                ccs_bars.append(c)
    # lg.debug(ccs_bars)
    return ccs_bars


def highlight(image, ccs_bars):
    """
    """
    RGB_image = image.to_rgb()
    for c in ccs_bars:
        RGB_image.highlight(c[0], RGBPixel(255, 0, 0))
    return RGB_image

def staff_line_position(image):
    """Finds the staff line position, but also corrects the output
    of the Miyao staff finder algorithm by connecting candidate
    sub-staves according to their position in the score, trying
    to glue related staves.

    Returns a vector with the vertices for each staff with the form 
    [(staff_number, x1, y1, x2, y2)], starting from number 1
    """

    stf_instance = musicstaves.StaffFinder_miyao(image, 0, 0)
    stf_instance.find_staves(5, 20, 0.8, -1) # 5 lines
    polygon = stf_instance.get_polygon()
    sc_position = [] # staff candidate
    stf_position = []


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

def system_position_parser(stf_position):
    """
    Returns the position of the systems
    """
    system_position = []
    system_position.append(stf_position[0])
    for j, s in enumerate(stf_position[1:]):
        if s[5] != system_position[-1][5]:
            system_position[-1].pop(3)
            system_position[-1].insert(3, stf_position[j][3])
            system_position[-1].pop(4)
            system_position[-1].insert(4, stf_position[j][4])
            system_position.append(s)    
    system_position[-1].pop(3)
    system_position[-1].insert(3, stf_position[-1][3])
    system_position[-1].pop(4)
    system_position[-1].insert(4, stf_position[-1][4])
    
    # lg.debug("system_position:\n{0}".format(system_position))
    return system_position




def bar_candidate_check(bar_candidates, stf_position):
    """
    Several methods to discard and/or validate bar candidates:

    1) Checks if the candidate bars lie within the upper and lower 
    boundaries of each staff. 

    2) Checks if bar candidate upper o lower position lies within a stf_position

    3) Creates a barline at the beginning of each staff according 
    to the staff position by the Miyao staff finder.

    Returns a vector in the form: [[gameracore.Image, staff_no]]
    """

    # lg.debug("SP: {0}".format(stf_position))
    checked_bars = []
    stf_height = sum([i[4]-i[2] for i in stf_position])/len(stf_position)
    # lg.debug("stf_height:{0}".format(stf_height))

    # retrieves the position of the systems
    system_position = system_position_parser(stf_position)    
    # lg.debug("system_position:\n{0}".format(system_position))

    for bc in bar_candidates:
        passes = True

        # discards a candidate if its mean y-position is above or below the first and last staff
        if bc.offset_y + ( bc.nrows - 1 ) / 2 < stf_position[0][2] or \
           bc.offset_y + ( bc.nrows - 1 ) / 2 > stf_position[len(stf_position) - 1][4]: 
            continue 

        # discards a candidate if it lies at the left of the closest staff
        for j, sp in enumerate(stf_position):
            if bc.offset_y > sp[2]:
                continue
            elif bc.offset_x < stf_position[j-1][1]:
                passes = False
                # lg.debug("Discarded {0} SP:{1}".format(bc, stf_position[j-1][1]))
                break
            else:
                break

        # Checks if bar candidate ul position lies within a stf_position
        for k, sp in enumerate(stf_position):
            passes = False
            if sp[2]-stf_height/8 < bc.offset_y < sp[4]+stf_height/8 or\
                sp[2]-stf_height/8 < bc.offset_y + bc.nrows - 1 < sp[4]+stf_height/8:
                passes = True
                break

        if passes == True:      
            checked_bars.append([bc, j+1])

    # Inserts bars at the beginning of each staff according to the staff x-position
    # for stf in stf_position:
    #     image = Image((stf[1], stf[2]), (stf[1]+5, stf[4]))
    #     image.draw_filled_rect((stf[1], stf[2]), (stf[1]+5, stf[4]), 1)
    #     checked_bars.append([image, stf[0]])

    return checked_bars

def bar_sorting(bar_vector):
    """
    Sorts a set of bars according to their staff number and x-position. Input vector should be:
    [staff_no, ux, uy, lx, ly]
    """
    checked_bars = sorted(bar_vector, key = lambda element: (element[0], element[1]))
    # lg.debug(checked_bars)
    return checked_bars

def system_structure_parser(system_input):
    """
    Parses the structure of the system according to the user input
    """
    system = system_input.split(',')
    output = []
    for i, s in enumerate(system):
        for j in range(int(s)):
            output.append(i+1)
    return output
    
def process_directory(input_folder, output_folder):
    for dirpath, dirnames, filenames in os.walk(input_folder):
        for f in filenames:
            # try:                
                if f.startswith("."):
                    continue

                filepath = os.path.join(dirpath, f)
                image = load_image(filepath)
                print filepath
                system_input = raw_input('System structure\n')
                system = system_structure_parser(system_input)

                image.save_tiff(os.path.join(output_folder, f.split('.')[0]+'_1_0_original.tiff'))

                #Applies a mask. Greyscale image needed
                if image.pixel_type_name != 'GreyScale':
                    image = image.to_greyscale()
                image = border_removal(image)
                image.save_tiff(os.path.join(output_folder, f.split('.')[0]+'_1_1_border_removed.tiff'))

                # Binarizes image
                binarized_image = image.to_onebit()
                # binarized_image.save_tiff(os.path.join(output_folder, f.split('.')[0]+'_0_bin.tiff'))

                # Auto-rotates an image
                image = image.correct_rotation(0)
                # image.save_tiff(os.path.join(output_folder, f.split('.')[0]+'_1_2_rotated.tiff'))

                # Returns the vertices for each staff and its number
                stf_position = staff_line_position(image)
                
                if len(stf_position) != len(system):
                    print 'Number of recognized staves is different to the one entered by the user'

                # Appends the proper system number according to the user input
                for i, s in enumerate(stf_position):
                    stf_position[i].append(system[i])
                # lg.debug(stf_position)


                stf_file = open(os.path.join(output_folder, f.split('.')[0]+'_staff_vertices.txt'), 'wb')
                # Saving staff bounding boxes
                for i, st in enumerate(stf_position):
                    line = '\t'.join([str(st[0]), str(st[1]), str(st[2]), str(st[3]), str(st[4]), str(system[i]), '\n'])
                    stf_file.write(line)
                stf_file.close()

                # Staff-line removal
                no_staff_image = staffline_removal(image)
                despeckle(no_staff_image)
                no_staff_image.save_tiff(os.path.join(output_folder, f.split('.')[0]+'_1_3_no_staff.tiff'))

                # Filters short-runs
                mfr = binarized_image.most_frequent_run('black', 'vertical')
                filtered_image = most_frequent_run_filter(no_staff_image, mfr)    # most_frequent_run

                # cc's and highlighs no staff and shrot runs filtered image and writes txt file with candidate bars
                ccs_bars = ccs(filtered_image)
                checked_bars = bar_candidate_check(ccs_bars, stf_position)
                RGB_image = highlight(image, checked_bars)
                RGB_image.save_tiff(os.path.join(output_folder, f.split('.')[0]+'_2_no_short_runs.tiff'))
                output_bar_file = open(os.path.join(output_folder, f.split('.')[0]+'_bar_position_2.txt'), 'wb')

                bar_list = []
                for c in checked_bars:
                    bar_list.append([c[1], c[0].offset_x, c[0].offset_y, c[0].offset_x+c[0].ncols-1, c[0].offset_y+c[0].nrows-1])

                sorted_bars = bar_sorting(bar_list)

                for bar in sorted_bars:
                    line = '\t'.join([str(bar[0]), str(bar[1]), str(bar[2]), str(bar[3]), str(bar[4]), '\n'])
                    output_bar_file.write(line)
                output_bar_file.close()

            # except:
                # lg.debug("Cannot process page {0}".format(f))
                # continue


if __name__ == "__main__":
    usage = "usage: %prog [options] input_folder output_folder"
    opts = OptionParser(usage = usage)
    options, args = opts.parse_args()
    init_gamera()

    process_directory(args[0], args[1])

    