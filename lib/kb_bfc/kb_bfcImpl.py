# -*- coding: utf-8 -*-
#BEGIN_HEADER
import os
import subprocess
import shutil
import uuid


from pprint import pprint
from ReadsUtils.ReadsUtilsClient import ReadsUtils
from KBaseReport.KBaseReportClient import KBaseReport

#END_HEADER


class kb_bfc:
    '''
    Module Name:
    kb_bfc

    Module Description:
    A KBase module: kb_bfc
    '''

    ######## WARNING FOR GEVENT USERS ####### noqa
    # Since asynchronous IO can lead to methods - even the same method -
    # interrupting each other, you must be *very* careful when using global
    # state. A method could easily clobber the state set by another while
    # the latter method is running.
    ######################################### noqa
    VERSION = "0.0.1"
    GIT_URL = "https://github.com/psdehal/kb_bfc.git"
    GIT_COMMIT_HASH = "4807d73b84af6bd6583dd2db8dc7d04b8e15efc3"

    #BEGIN_CLASS_HEADER
    BFC = '/kb/module/bfc/bfc'
    SEQTK = '/kb/module/seqtk/seqtk'

    THREADS = 8
    #END_CLASS_HEADER

    # config contains contents of config file in a hash or None if it couldn't
    # be found
    def __init__(self, config):
        #BEGIN_CONSTRUCTOR

        self.scratch = os.path.abspath(config['scratch'])
        self.callbackURL = os.environ['SDK_CALLBACK_URL']

        if not os.path.exists(self.scratch):
            os.makedirs(self.scratch)

        #END_CONSTRUCTOR
        pass


    def run_bfc(self, ctx, params):
        """
        :param params: instance of type "BFCParams" -> structure: parameter
           "input_reads_upa" of type "reads_upa" (unique permanent address of
           reads object), parameter "workspace_name" of String, parameter
           "output_reads_name" of String, parameter "kmer_size" of Long,
           parameter "drop_unique_kmer_reads" of type "bool" (A boolean. 0 =
           false, anything else = true.), parameter "est_genome_size" of
           Long, parameter "est_genome_size_units" of String
        :returns: instance of type "BFCResults" -> structure: parameter
           "report_name" of String, parameter "report_ref" of String
        """
        # ctx is the context object
        # return variables are: results
        #BEGIN run_bfc

        print('Running run_bfc with params=')
        pprint(params)
        bfc_cmd = [self.BFC]
        shared_dir = "/kb/module/work/tmp"

        #validate parameters
        if 'workspace_name' not in params:
            raise ValueError('workspace_name parameter is required')
        if 'input_reads_upa' not in params:
            raise ValueError('input_reads_upa parameter is required')
        if 'output_reads_name' not in params:
            raise ValueError('output_reads_name parameter is required')

        if 'drop_unique_kmer_reads' in params:
            if params['drop_unique_kmer_reads']:
                bfc_cmd.append(str('-1'))

        if 'est_genome_size' in params:
            if params['est_genome_size']:
                if 'est_genome_size_units' in params:
                    if params['est_genome_size_units'] in ["G", "M", "K", "g", "m", "k"]:
                        bfc_cmd.append('-s')
                        bfc_cmd.append(str(params['est_genome_size']) + str(params['est_genome_size_units']))
                    else:
                        raise ValueError('est_genome_size_units must be G, M or K')
                else:
                    raise ValueError('est_genome_size_units must be set')

        if 'kmer_size' in params:
            if params['kmer_size']:
                if params['kmer_size'] < 64:
                    bfc_cmd.append('-k')
                    bfc_cmd.append(str(params['kmer_size']))
                else:
                    raise ValueError('kmer_size must be <= 63')



        input_reads_upa = params['input_reads_upa']
        output_reads_name = params['output_reads_name']

        output_reads_file = os.path.join(shared_dir, output_reads_name + ".fq")
        bfc_output_file = os.path.join(shared_dir, "bfc_" + output_reads_name + ".fq")
        seqtk_output_file = os.path.join(shared_dir, "seqtk_bfc_" + output_reads_name + ".fq")
        workspace_name = params['workspace_name']

        #get the reads library as gzipped interleaved file
        reads_params = {'read_libraries': [input_reads_upa],
                        'interleaved': 'true',
                        'gzipped': 'true'
                        }

        ru = ReadsUtils(self.callbackURL)
        reads = ru.download_reads(reads_params)['files']
        input_reads_file = reads[input_reads_upa]['files']['fwd']
        print('Input reads files:')
        pprint('     ' + input_reads_file)

        #hardcoding a couple parameters
        bfc_cmd.append('-t')
        bfc_cmd.append(str(self.THREADS))

        bfc_cmd.append(input_reads_file)

        bfc_cmd.append('>')
        bfc_cmd.append(bfc_output_file)

        print('Running BFC:')
        print('     ' + ' '.join(bfc_cmd))

        p=subprocess.Popen(" ".join(bfc_cmd), cwd=self.scratch, shell=True)
        retcode = p.wait()

        if p.returncode != 0:
            raise ValueError('Error running bfc, return code: ' + str(retcode) + "\n")

        #drop non-paired reads using seqtk

        seqtk_cmd = [self.SEQTK, "dropse", bfc_output_file, ">", seqtk_output_file]

        p = subprocess.Popen(" ".join(seqtk_cmd), cwd=self.scratch, shell=True)
        retcode = p.wait()

        if p.returncode != 0:
            raise ValueError('Error running seqtk, return code: ' + str(retcode) + "\n")

        #upload reads output
        shutil.copy(seqtk_output_file, output_reads_file)

        out_reads_upa = ru.upload_reads({'fwd_file': output_reads_file,
                                        'interleaved': 1, 'wsname': workspace_name,
                                        'name': output_reads_name,
                                        'source_reads_ref': input_reads_upa
                                        })

        #create report

        report = ''
        report += 'Successfully ran bfc, with command: ' + ' '.join(bfc_cmd)
        report += "\n"
        report += 'created object: '
        report += out_reads_upa['obj_ref']

        print('Saving report')
        kbr = KBaseReport(self.callbackURL)
        try:
            report_info = kbr.create_extended_report(
                {
                'message': report,
                'objects_created': [{'ref': out_reads_upa['obj_ref'], 'description': 'Corrected reads'}],
                'workspace_name':workspace_name,
                #'direct_html_link_index':0,
                'report_object_name': 'bfc_report_' + str(uuid.uuid4())
                })
        except:
            print("exception from saving report")
            raise

        results = {'report_name': report_info['name'], 'report_ref': report_info['ref']}

        #END run_bfc

        # At some point might do deeper type checking...
        if not isinstance(results, dict):
            raise ValueError('Method run_bfc return value ' +
                             'results is not type dict as required.')
        # return the results
        return [results]
    def status(self, ctx):
        #BEGIN_STATUS
        returnVal = {'state': "OK",
                     'message': "",
                     'version': self.VERSION,
                     'git_url': self.GIT_URL,
                     'git_commit_hash': self.GIT_COMMIT_HASH}
        #END_STATUS
        return [returnVal]
