import argparse
import datetime
import os

from pymei import XmlImport, XmlExport, MeiElement
# set up command line argument structure
parser = argparse.ArgumentParser(description='Combines mei files created by the barline finding algorithm')
parser.add_argument('inputdirectory', help='input directory')
parser.add_argument('fileout', help='output file (.mei)')
parser.add_argument('-v', '--verbose', help='increase output verbosity', action='store_true')

class MeiCombiner:
    '''
    Combines mei files created by the barline finding algorithm.
    '''

    def __init__(self, input_mei_paths, output_mei_path):
        '''
        PARAMETERS
        ----------
        input_mei_paths {list}: list of mei paths to combine
        output_mei_path {String}: output file path of type .mei
        '''

        self.input_mei_paths = input_mei_paths
        self.output_mei_path = output_mei_path
        if len(self.input_mei_paths):
            self.meidoc = XmlImport.documentFromFile(self.input_mei_paths[0])
        else:
            self.meidoc = None

    def combine(self):
        if self.meidoc and len(input_mei_paths) > 1:
            base_facsimile = self.meidoc.getElementsByName('facsimile')[0]
            base_section = self.meidoc.getElementsByName('section')[0]
            for f in self.input_mei_paths[1:]:
                mei = XmlImport.documentFromFile(f)

                # combine surface
                surface = mei.getElementsByName('surface')
                if len(surface):
                    # have to remove the child from the old document in memory
                    # or else pymei segfaults ...
                    surface[0].getParent().removeChild(surface[0])
                    base_facsimile.addChild(surface[0])

                # combine measures
                pb = MeiElement('pb')
                base_section.addChild(pb)

                # get last measure number
                measures = base_section.getChildrenByName('measure')
                last_measure_n = int(measures[-1].getAttribute('n').value)

                new_section = mei.getElementsByName('section')[0]
                music_elements = new_section.getChildren()

                for e in music_elements:
                    if e.getName() == 'measure':
                        last_measure_n += 1
                        e.addAttribute('n', str(last_measure_n))

                    base_section.addChild(e)

                # remove all musical elements from the old document or else pymei segfaults
                new_section.getParent().deleteAllChildren()

            self._add_revision()

    def _add_revision(self):
        # add a revision
        today = datetime.date.today().isoformat()
        change = MeiElement('change')

        # get last change number
        changes = self.meidoc.getElementsByName('change')
        if len(changes):
            last_change = int(changes[-1].getAttribute('n').value)

        change.addAttribute('n', str(last_change+1))
        resp_stmt = MeiElement('respStmt')
        corp_name = MeiElement('corpName')
        corp_name.setValue('Distributed Digital Music Archives and Libraries Lab (DDMAL)')
        change_desc = MeiElement('changeDesc')
        ref = MeiElement('ref')
        p = MeiElement('p')
        application = self.meidoc.getElementsByName('application')
        app_name = 'RODAN/barlineFinder'
        if len(application):
            ref.addAttribute('target', '#'+application[0].getId())
            ref.setValue(app_name)
            ref.setTail('.')
            p.addChild(ref)

        p.setValue('Combining individual page MEIs using ')
        date = MeiElement('date')
        date.setValue(today)

        revision_descs = self.meidoc.getElementsByName('revisionDesc')
        if len(revision_descs):
            revision_descs[0].addChild(change)
            change.addChild(resp_stmt)
            resp_stmt.addChild(corp_name)
            change.addChild(change_desc)
            change_desc.addChild(p)
            change.addChild(date)

    def write_mei(self):
        if self.meidoc:
            XmlExport.meiDocumentToFile(self.meidoc, self.output_mei_path)

if __name__ == "__main__":
    # parse command line arguments
    args = parser.parse_args()
    input_directory = args.inputdirectory
    
    input_mei_paths = []
    # get mei files in the input directory
    for dirpath, dirnames, filenames in os.walk(input_directory):
        for f in filenames:
            if f.startswith('.'):
                continue
            elif f.endswith('.mei'):
                filepath = os.path.join(dirpath, f)
                input_mei_paths.append(filepath)

    output_file = args.fileout
    verbose = args.verbose

    mc = MeiCombiner(input_mei_paths, output_file)
    mc.combine()
    mc.write_mei()
