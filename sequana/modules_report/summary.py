# coding: utf-8
#
#  This file is part of Sequana software
#
#  Copyright (c) 2016 - Sequana Development Team
#
#  File author(s):
#      Dimitri Desvillechabrol <dimitri.desvillechabrol@pasteur.fr>,
#          <d.desvillechabrol@gmail.com>
#
#  Distributed under the terms of the 3-clause BSD license.
#  The full license is in the LICENSE file, distributed with this software.
#
#  website: https://github.com/sequana/sequana
#  documentation: http://sequana.readthedocs.io
#
##############################################################################
"""Module to write summary.html have all information about the pipeline and
to visit other analysis"""
import os

from sequana.lazy import pandas as pd

import easydev
from sequana.modules_report.base_module import SequanaBaseModule
from sequana.utils import config
from sequana.utils.datatables_js import DataTable
from sequana.snaketools import SnakeMakeStats

class SummaryModule(SequanaBaseModule):
    """ Write summary HTML report of an analysis. It contains all information
    about the pipeline used, input/output files and version of software.
    """
    def __init__(self, data):
        """
        """
        super().__init__()
        self.json = data
        self.title = "Sequana Report Summary"
        self.create_report_content()
        self.create_html("summary.html")
        
    def create_report_content(self):
        """ Create the report content.
        """
        self.sections = list()

        self.pipeline_inputs()
        self.pipeline_outputs()
        # TODO add customs sections from other reports
        self.workflow()
        self.running_stats()
        self.dependencies()

    def pipeline_inputs(self):
        """ Link to inputs analysed.
        """
        # copy inputs in the input directory
        input_dir = "inputs"
        inputs = [self.copy_file(i, input_dir) for i in self.json['inputs']] 
        # create links list
        html_list = '<li>{0}</li>'
        links = [html_list.format(self.create_link(os.path.basename(i), i,
                 newtab=False, download=True)) for i in inputs]
        links = '<ul>{0}</ul>'.format("\n".join(links))
        self.sections.append({
            'name': 'Inputs',
            'anchor': 'input',
            'content':
                "<p>Link to the original data analysed.</p>\n"
                "{0}".format(links)
        })

    def pipeline_outputs(self):
        """ Link to important output generate by the pipeline
        """
        # copy outputs in the output directory
        output_dir = "outputs"
        outputs = [self.copy_file(i, output_dir) for i in self.json['outputs']] 
        # create links list
        html_list = '<li>{0}</li>'
        links = [html_list.format(self.create_link(os.path.basename(i), i,
                 newtab=False, download=True)) for i in outputs]
        links = '<ul>{0}</ul>'.format("\n".join(links))
        self.sections.append({
            'name': 'Outputs',
            'anchor': 'outputs',
            'content':
                "<p>Link to the most important outputs files generated by the "
                "pipeline.</p>\n{0}".format(links)
        })

    def workflow(self):
        """ Create the interactive DAG to navigate through pages.
        """
        # move the SVG file in the images directory
        img = self.copy_file(self.json['rulegraph'], '.')
        dag_svg = self.include_svg_image(img)
        with open(self.json['snakefile'], 'r') as fp:
            code = self.add_code_section(fp.read(), 'python')
        sf = self.create_hide_section('Sf', "Show/hide Snakemake file",code,
                                      hide=True)
        sf = "\n".join(sf)
        with open(self.json['config'], 'r') as fp:
            code = self.add_code_section(fp.read(), 'yaml')
        c = self.create_hide_section('C', "Show/hide config file", code,
                                     hide=True)
        c = "\n".join(c)
        self.sections.append({
            'name': 'Workflow',
            'anchor': 'workflow',
            'content':
                "<p>The following network shows the workflow of the pipeline. "
                "Blue boxes are clickable and redirect to dedicated reports."
                "</p>\n{0}\n"
                "<p>The analysis was performed with the following Snakemake "
                "and config file:</p>\n"
                "<u><li>{1}</li>\n<li>{2}</li></u>\n".format(dag_svg, sf, c)
        })

    def running_stats(self):
        """ Barplot that shows computing time of each rule.
        """
        try:
            stats = SnakeMakeStats(self.json['stats'])
        except KeyError:
            return
        png = self.create_embedded_png(stats.plot_and_save, 'filename',
                                       outputdir=None)
        l, c = self.create_hide_section('Stats', 'collapse/expand', png, True)
        self.sections.append({
            'name': "Running Stats {0}".format(self.add_float_right(l)),
            'anchor': 'stats',
            'content': c
        })

    def dependencies(self):
        """ Table with all python dependencies and a text file with tools
        needed and its versions.
        """
        html_table = self.get_table_dependencies()
        pypi = self.create_link('Pypi', 'http://pypi.python.org')
        req = self.create_link('requirements', self.json['requirements'])
        content = ("<p>Python dependencies (<b>{0}</b>){1}</p>"
                   "<p>Dependencies downloaded from bioconda "
                   "<b>{2}</b></p>".format(pypi, html_table, req))
        l, c = self.create_hide_section('Dep', 'collapse/expand', content,
                                        hide=True)
        self.sections.append({
            'name': "Dependencies {0}".format(self.add_float_right(l)),
            'anchor': 'dependencies',
            'content': c
        })

    def get_table_dependencies(self):
        """ Return dependencies of sequana.
        """
        dep_list = easydev.get_dependencies('sequana')
        project_name = list()
        version = list()
        link = list()
        pypi = 'https://pypi.python.org/pypi/{0}'
        for dep in dep_list:
            version.append(dep.version)
            project_name.append(dep.project_name)
            link.append(pypi.format(dep.project_name))
        df = pd.DataFrame({'package': project_name, 'version': version, 
                           'link': link})
        df['sort'] = df['package'].str.lower()
        df.sort_values(by='sort', axis=0, inplace=True)
        df.drop('sort', axis=1, inplace=True)
        datatable = DataTable(df, 'dep')
        datatable.datatable.datatable_options = {'paging': 'false',
                                                 'bFilter': 'false',
                                                 'bInfo': 'false',
                                                 'bSort': 'false'}
        datatable.datatable.set_links_to_column('link', 'package')
        js = datatable.create_javascript_function()
        html = datatable.create_datatable(index=False)
        return js + '\n' + html
