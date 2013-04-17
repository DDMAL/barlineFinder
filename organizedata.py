# script to organize dataroot for evaluation

import os
import shutil

if __name__ == "__main__":
    input_dataroot = '/Volumes/Shared/IMSLP/TESTS/dataroot'
    output_dataroot = '/Volumes/MarkovProperty/gburlet/work/DetmoldBarFinder/barlineFinder/data'

    for dirpath, dirnames, filenames in os.walk(input_dataroot):
        # get txt files
        txt_files = [f for f in filenames if f.endswith('.txt')]
        img_files = [f for f in filenames if f.endswith('.tiff')]
        gt_files = [f for f in filenames if f.endswith('.mei') and not f.endswith('_ao.mei')]
        ao_files = [f for f in filenames if f.endswith('_ao.mei')]
        txt_files.sort()
        img_files.sort()
        gt_files.sort()
        ao_files.sort()

        if len(txt_files) != len(img_files) != len(gt_files) != len(ao_files):
            raise ValueError('number of files do not match up')

        # for each datapoint
        for i in range(len(img_files)):
            datapoint_number = ('%d' % (i+1)).zfill(3)
            datapoint_path = os.path.join(output_dataroot, datapoint_number)
            os.makedirs(datapoint_path)

            i_txt_file = os.path.join(input_dataroot, txt_files[i])
            i_img_file = os.path.join(input_dataroot, img_files[i])
            i_gt_file = os.path.join(input_dataroot, gt_files[i])
            i_ao_file = os.path.join(input_dataroot, ao_files[i])

            o_txt_file = os.path.join(datapoint_path, txt_files[i])
            o_img_file = os.path.join(datapoint_path, img_files[i])
            o_gt_file = os.path.join(datapoint_path, gt_files[i])
            o_ao_file = os.path.join(datapoint_path, ao_files[i])

            shutil.copy(i_txt_file, o_txt_file)
            shutil.copy(i_img_file, o_img_file)
            shutil.copy(i_gt_file, o_gt_file)
            shutil.copy(i_ao_file, o_ao_file)
