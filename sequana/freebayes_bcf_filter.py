# -*- coding: utf-8 -*-
#
#  This file is part of Sequana software
#
#  Copyright (c) 2016 - Sequana Development Team
#
#  File author(s):
#      Thomas Cokelaer <thomas.cokelaer@pasteur.fr>
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
"""Analysis of VCF file generated by freebayes. This method need the version
0.10 of pysam.
"""
from pysam import VariantFile
from sequana.lazy import pandas as pd
from sequana import logger


class Variant(object):
    """ Variant class to stock variant reader and dictionary that resume most
    important informations.
    """
    def __init__(self, record):
        """.. rubric:: constructor

        :param RecordVariant record: variant record
        :param dict resume: most important informations of variant
        """
        self._record = record
        self._resume = self._bcf_line_to_dict(record)

    def __str__(self):
        return str(self.record)

    @property
    def record(self):
        return self._record

    @property
    def resume(self):
        return self._resume

    def _bcf_line_to_dict(self, bcf_line):
        """ Convert a BCF line as a dictionnary with the most important
        information to detect real variants.
        """
        # Calcul all important information
        alt_freq = compute_freq(bcf_line)
        strand_bal = compute_strand_bal(bcf_line)
        line_dict = {"chr": bcf_line.chrom, "position": str(bcf_line.pos),
                     "depth": bcf_line.info["DP"], "reference": bcf_line.ref,
                     "alternative": "; ".join(str(x) for x in bcf_line.alts),
                     "freebayes_score": bcf_line.qual,
                     "strand_balance": "; ".join(
                         "{0:.2f}".format(x) for x in strand_bal),
                     "frequency": "; ".join(
                         "{0:.2f}".format(x) for x in alt_freq)}
        try:
            # If bcf is annotated by snpEff
            annotation = bcf_line.info["EFF"][0].split("|")
            effect_type, effect_lvl = annotation[0].split("(")
            try:
                prot_effect, cds_effect = annotation[3].split("/")
            except ValueError:
                cds_effect = annotation[3]
                prot_effect = ""
            ann_dict = {"CDS_position": cds_effect[2:],
                        "effect_type": effect_type,
                        "codon_change": annotation[2],
                        "gene_name": annotation[5],
                        "mutation_type": annotation[1],
                        "prot_effect": prot_effect[2:],
                        "prot_size": annotation[4],
                        "effect_impact": effect_lvl}
            line_dict = dict(line_dict, **ann_dict)
        except KeyError:
            pass
        return line_dict


class BCF_freebayes(VariantFile):
    """ BCF_freebayes class (Binary Variant Calling Format)

    This class is a wrapping of VariantFile class from the pysam package. It
    is dedicated for VCF file generated by freebayes and compressed by
    bcftools. BCF file is faster to parse than VCF. A data frame with all
    variants is produced which can be write as csv file. It can filter variants
    with a dictionnary of filter parameter. Filter variants are wrotte in a new
    VCF file.

    Example:

    ::

        from sequana import sequana_data, BCF_freebayes
        bcf_filename = sequana_data("test.bcf", "testing")

        # Read the data
        b = BCF_freebayes(bcf_filename)

        # Filter the data
        filter_dict = {'freebayes_score': 200,
                       'frequency': 0.8,
                       'min_depth': 10,
                       'forward_depth':3,
                       'reverse_depth':3,
                       'strand_ratio': 0.2}
        b.filter_bcf(filter_dict, "output.vcf")
    """
    def __init__(self, input_filename, **kwargs):
        """
        :param str filename: a bcf file.
        :param kwargs: any arguments accepted by VariantFile.
        """
        try:
            super().__init__(input_filename, **kwargs)
        except OSError:
            logger.error("OSError: {0} doesn't exist.".format(input_filename))
            raise OSError
        # initiate filters dictionary
        self._filters = {'freebayes_score': 0,
                         'frequency': 0,
                         'min_depth': 0,
                         'forward_depth':0,
                         'reverse_depth':0,
                         'strand_ratio': 0}

    @property
    def filters(self):
        """ Get or set the filters parameters to select variants of interest.
        Setter take a dictionnary as parameter to update the attribute 
        :attr:`BCF_freebayes.filters`. Delete will reset different variable to
        0.

        ::

            bcf = BCF_freebayes("input.bcf")
            bcf.filter = {"freebayes_score": 200,
                          "frequency": 0.8,
                          "min_depth": 10,
                          "forward_depth":3,
                          "reverse_depth":3,
                          "strand_ratio": 0.2}
        """
        return self._filters

    @filters.setter
    def filters(self, d):
        self._filters.update(d)

    @filters.deleter
    def filters(self):
        self._filters = {"freebayes_score": 0,
                         "frequency": 0,
                         "min_depth": 0,
                         "forward_depth":0,
                         "reverse_depth":0,
                         "strand_ratio": 0}

    def filter_bcf(self, filter_dict=None):
        """ Filter variants in the BCF file and write them in a BCF file.

        :param str output_filename: BCF output filename.
        :param dict filter_dict: dictionary of filters. It updates the
            attribute :attr:`BCF_freebayes.filters`
        Return BCF_freebayes object with new BCF file.
        """
        if filter_dict:
            self.filters = filter_dict
        variants = [Variant(v) for v in self if self._filter_line(v)]
        # Rewind the iterator
        self.reset()
        return Filtered_freebayes(variants, self)

    def _filter_line(self, bcf_line):
        """ Filter variant with parameter set in :attr:`BCF_freebayes.filters`.

        :param VariantRecord bcf_line

        Return line if all filters are passed.
        """
        if bcf_line.qual < self.filters["freebayes_score"]:
            return False

        if bcf_line.info["DP"] <= self.filters["min_depth"]:
            return False

        forward_depth = bcf_line.info["SRF"] + sum(bcf_line.info["SAF"])
        if forward_depth <= self.filters["forward_depth"]:
            return False

        reverse_depth = bcf_line.info["SRR"] + sum(bcf_line.info["SAR"])
        if reverse_depth <= self.filters["reverse_depth"]:
            return False

        alt_freq = compute_freq(bcf_line)
        if alt_freq[0] < self.filters["frequency"]:
            return False

        strand_bal = compute_strand_bal(bcf_line)
        if strand_bal[0] < self.filters["strand_ratio"]:
            return False

        return True


class Filtered_freebayes(object):
    """ Variants filtered with BCF_freebayes.
    """
    _col_index = ['chr', 'position', 'reference', 'alternative', 'depth',
                  'frequency', 'strand_balance', 'freebayes_score',
                  'effect_type', 'mutation_type', 'effect_impact', 'gene_name',
                  'CDS_position', 'codon_change', 'prot_effect', 'prot_size']
    def __init__(self, variants, bcf):
        """.. rubric:: constructor

        :param list variants: list of variants record.
        :param BCF_freebayes bcf: class parent.
        """
        self._variants = variants
        self._bcf = bcf
        self._df = self._bcf_to_df()

    @property
    def variants(self):
        """ Get the variant list.
        """
        return self._variants

    @property
    def df(self):
        return self._df

    def _bcf_to_df(self):
        """ Create a data frame with the most important information contained
        in the bcf file.
        """
        dict_list = [v.resume for v in self.variants]
        df = pd.DataFrame.from_records(dict_list)
        try:
            df = df[Filtered_freebayes._col_index]
        except (ValueError, KeyError):
            df = df[Filtered_freebayes._col_index[:len(df.columns)]]
        return df

    def to_csv(self, output_filename):
        """ Write DataFrame in CSV format.

        :params str output_filename: output CSV filename.
        """
        with open(output_filename, "w") as fp:
            print("# sequana_variant_calling; {0}".format(self._bcf.filters),
                  file=fp)
            if self.df.empty:
                print(",".join(Filtered_freebayes._col_index), file=fp)
            else:
                self.df.to_csv(fp, index=False)

    def to_vcf(self, output_filename):
        """ Write BCF file in VCF format.

        :params str output_filename: output VCF filename.
        """
        with open(output_filename, "w") as fp:
            print(self._bcf.header, end="", file=fp)
            for variant in self.variants:
                print(variant, end="", file=fp)


def strand_ratio(number1, number2):
    """ Compute ratio between two number. Return result between [0:0.5].
    """
    try:
        division = float(number1) / (number1 + number2)
        if division > 0.5:
            division = 1 - division
    except ZeroDivisionError:
        return 0
    return division

def compute_freq(bcf_line):
    """ Compute frequency of alternate allele.
        alt_freq = Count Alternate Allele / Depth

        :param VariantRecord bcf_line: variant record
    """
    alt_freq = [float(count)/bcf_line.info["DP"]
                for count in bcf_line.info["AO"]]
    return alt_freq

def compute_strand_bal(bcf_line):
    """ Compute strand balance of alternate allele include in [0,0.5].
        strand_bal = Alt Forward / (Alt Forward + Alt Reverse)

    """
    strand_bal = [
        strand_ratio(bcf_line.info["SAF"][i], bcf_line.info["SAR"][i])
        for i in range(len(bcf_line.info["SAF"]))]
    return strand_bal
