from optparse import OptionParser
import os

from gamera.core import *

from barfinder import BarlineFinder
from meicreate import BarlineDataConverter


if __name__ == "__main__":
    init_gamera()
    usage = "usage: %prog input_folder output_folder"
    opts = OptionParser(usage = usage)
    options, args = opts.parse_args()

    input_folder = args[0]
    output_folder = args[1]
    done = 0
    failed = 0

    


    for dirpath, dirnames, filenames in os.walk(args[0]):
        for f in filenames[:]:
            fullPath = os.path.join(input_folder, f)
            fileName, fileExtension = os.path.splitext(fullPath)
            # print fileName, fileExtension
            output_mei_file = os.path.join(output_folder, os.path.splitext(f)[0] + '_ao.mei')

            if fileExtension == ".tiff" and os.path.isfile(output_mei_file) is not True:
                print "IMAGE TIFF :{0}".format(f)

            try:
                txt_file = open(os.path.join(fileName + '.txt'), 'rb')
                sg_hint = txt_file.readlines()[0]
                

                noborderremove = '-nb'
                norotation = ''
                verbose = ''

                bar_finder = BarlineFinder()
                staff_bb, bar_bb, image_path, image_width, image_height, image_dpi = bar_finder.process_file(fullPath, sg_hint, noborderremove, norotation)
                # print 'STAFF_BB:{0}\nBAR_BB:{1}'.format(staff_bb, bar_bb)
                bar_converter = BarlineDataConverter(staff_bb, bar_bb, verbose)
                bar_converter.bardata_to_mei(sg_hint, image_path, image_width, image_height, image_dpi)
                bar_converter.output_mei(output_mei_file)
                print 'DONE!\n'
                done += 1
                
            except Exception, e:
                print 'FAILED!\n'
                log_file = open('filechecker_output_log.txt', 'a')
                log_file.write('\t'.join([f, str(e), '\n']))
                log_file.close()
                failed += 1
                continue

    print "\nDONE: {0}\nFAILED: {1}".format(done, failed)


            # except:
            #     print 'PROBLEM WITH FILE: {0}\n'.format(fullPath)
            #     continue

