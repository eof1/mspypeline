import pandas as pd
import numpy as np
import os
import sys
from Logger import Logger
from matplotlib_venn import venn3, venn2
import matplotlib.pyplot as plt
from scipy import stats
from itertools import combinations
from collections import defaultdict as ddict
from ruamel.yaml import YAML
from tkinter import filedialog


class MQInitializer(Logger):
    def __init__(self, dir_: str, file_path_yml: str = None):
        super().__init__(self.__class__.__name__)
        self._replicates = None
        self._replicate_representation = None
        self._min_number_replicates = None
        self._max_number_replicates = None
        self._replicates_representation = None

        self.script_loc = os.path.dirname(os.path.realpath(__file__))
        self.path_pipeline_config = os.path.join(self.script_loc, "config")

        self.yml_file_name_tmp = "config_tmp.yml"
        self.yml_file_name = "config.yml"
        self.default_yml_name = "ms_analysis_default.yml"

        # make sure to be on the right level and set starting dir
        if os.path.split(os.path.split(dir_)[0])[-1] == "txt":
            self.logger.debug("Removing txt ending from path")
            self.start_dir = os.path.join(os.path.split(os.path.split(dir_)[0])[0])
        else:
            self.start_dir = dir_
        self.logger.info(f"Starting dir: {self.start_dir}")

        # if no yml file is passed try to guess it or ask for one
        if file_path_yml is None:
            file_path_yml = self.init_yml_path()
        elif file_path_yml.lower() == "default":
            file_path_yml = self.get_default_yml_path()

        # load the config from the yml file
        self.logger.debug(f"yml file location: {file_path_yml}")
        self.yaml = YAML()
        self.yaml.default_flow_style = False
        self.logger.info("loading yml file")
        with open(file_path_yml) as f:
            self.configs = self.yaml.load(f)
        self.logger.debug(f"Config file contents: {self.configs}")

        self.path_config = os.path.join(self.start_dir, "config")
        os.makedirs(self.path_config, exist_ok=True)
        self.update_config_file()

        # read the proteinGroups.txt and peptides.txt
        self.logger.info("Reading proteinGroups.txt")  # TODO also reading another file
        self.df_protein_names, self.df_peptide_names = self.init_dfs_from_txts()
        self.update_config_file()

        # read all proteins and receptors of interest from the config dir
        self.logger.info("Reading proteins and receptors of interest")
        self.interesting_proteins, self.interesting_receptors, self.go_analysis_gene_names = self.init_interest_from_xlsx()

    @property
    def replicates(self):
        if self._replicates is None:
            self._replicates = self.init_replicates(self.df_protein_names.columns)
        return self._replicates

    def init_replicates(self, df_colnames):
        all_reps = sorted([x.replace('Intensity ', '') for x in df_colnames
                           if x.startswith('Intensity ')], key=len, reverse=True)
        _replicates = ddict(list)
        for experiment in self.configs.get("experiments", False):
            if not experiment:
                raise ValueError("Missing experiments key in config file")
            for rep in all_reps:
                if rep.startswith(experiment):
                    _replicates[experiment].append(rep)
        return _replicates

    def get_default_yml_path(self):
        self.logger.debug(f"Loading default yml file from: {self.script_loc}, since no file was selected")
        if self.default_yml_name in os.listdir(self.path_pipeline_config):
            yaml_file = os.path.join(self.path_pipeline_config, self.default_yml_name)
        else:
            raise ValueError("Could not find default yaml file. Please select one.")
        return yaml_file

    def init_yml_path(self) -> str:
        def yml_file_dialog() -> str:
            file_path = filedialog.askopenfilename()
            self.logger.debug(f"selected file path: {file_path}")
            if not file_path:
                yaml_file = self.get_default_yml_path()
            elif not file_path.endswith(".yaml") and not file_path.endswith(".yml"):
                raise ValueError("Please select a yaml / yml file")
            else:
                yaml_file = file_path
            return yaml_file

        if "config" in os.listdir(self.start_dir):
            self.logger.debug("Found config dir")
            config_dir = os.path.join(self.start_dir, "config")
            if self.yml_file_name in os.listdir(config_dir):
                self.logger.debug("Found config.yml file in config dir")
                yaml_file = os.path.join(config_dir, self.yml_file_name)
            else:
                yaml_file = yml_file_dialog()
        else:
            yaml_file = yml_file_dialog()
        return yaml_file

    def init_dfs_from_txts(self):
        file_dir_txt = os.path.join(self.start_dir, "txt")
        if not os.path.isdir(file_dir_txt):
            raise ValueError("Directory does not contain a txt dir")
        file_dir_protein_names = os.path.join(file_dir_txt, "proteinGroups.txt")
        file_dir_peptides_names = os.path.join(file_dir_txt, "peptides.txt")
        # make sure protein groups file exists
        if not os.path.isfile(file_dir_protein_names):
            raise ValueError("txt directory does not contain a proteinGroups.txt file")
        if not os.path.isfile(file_dir_peptides_names):
            raise ValueError("txt directory does not contain a peptides.txt file")
        # read protein groups file
        df_protein_names = pd.read_csv(file_dir_protein_names, sep="\t")
        df_peptide_names = pd.read_csv(file_dir_peptides_names, sep="\t")

        # try to automatically determine experimental setup
        if not self.configs.get("experiments", False):
            self.logger.info("No replicates specified in settings file. Trying to infer.")
            # TODO will there every be more than 9 replicates?
            import difflib

            def get_overlap(s1, s2):
                s = difflib.SequenceMatcher(None, s1, s2)
                pos_a, pos_b, size = s.find_longest_match(0, len(s1), 0, len(s2))
                return s1[pos_a:pos_a + size]

            # TODO can the Intensity column always be expected in the file?
            # TODO will the column names always be the same between Intensity and LFQ intensity?
            all_reps = sorted([x.replace('Intensity ', '') for x in df_protein_names.columns
                               if x.startswith('Intensity ')], key=len, reverse=True)
            # make sure the two files contain the same replicate names
            all_reps_peptides = [x.replace('Intensity ', '') for x in df_protein_names.columns
                                 if x.startswith('Intensity ')]
            experiment_analysis_overlap = [x not in all_reps for x in all_reps_peptides]
            if any(experiment_analysis_overlap):
                unmatched = [x for x in all_reps_peptides if experiment_analysis_overlap]
                raise ValueError("Found replicates in peptides.txt, but not in proteinGroups.txt: " +
                                 ", ".join(unmatched))
            #
            overlap = [[get_overlap(re1, re2) if re1 != re2 else "" for re1 in all_reps] for re2 in all_reps]
            overlap_matrix = pd.DataFrame(overlap, columns=all_reps, index=all_reps)
            unclear_matches = []
            replicates = ddict(list)
            for col in overlap_matrix:
                sorted_matches = sorted(overlap_matrix[col].values, key=len, reverse=True)
                best_match = sorted_matches[0]
                replicates[best_match].append(col)
                # check if any other match with the same length could be found
                if any([len(best_match) == len(match) and best_match != match for match in sorted_matches]):
                    unclear_matches.append(best_match)
            for experiment in replicates:
                if len(replicates[experiment]) == 1:
                    rep = replicates.pop(experiment)
                    replicates[rep[0]] = rep
                elif experiment in unclear_matches:
                    self.logger.debug(f"unclear match for experiment: {experiment}")
            self.logger.info(f"determined experiemnts: {replicates.keys()}")
            self.logger.debug(f"number of replicates per experiment:")
            self.logger.debug("\n".join([f"{ex}: {len(replicates[ex])}" for ex in replicates]))
            self.configs["experiments"] = list(replicates.keys())
            self._replicates = replicates

        # TODO properties seem to make no sense here anymore
        if self._replicates is None:
            self._replicates = self.init_replicates(df_protein_names.columns)

        found_replicates = [rep for l in self.replicates.values() for rep in l]
        for df_cols in [df_peptide_names.columns, df_protein_names.columns]:
            intens_cols = [x.replace('Intensity ', '') for x in df_cols if x.startswith('Intensity ')]
            not_found_replicates = [x not in found_replicates for x in intens_cols]
            if any(not_found_replicates):
                unmatched = [x for x in intens_cols if not_found_replicates]
                raise ValueError("Found replicates in peptides.txt, but not in proteinGroups.txt: " +
                                 ", ".join(unmatched))

        # filter all contaminants by removing all rows where any of the 3 columns contains a +
        not_contaminants = (df_protein_names[
                                ["Only identified by site", "Reverse", "Potential contaminant"]] == "+"
                            ).sum(axis=1) == 0
        df_protein_names = df_protein_names[not_contaminants]
        # split the fasta headers
        # first split all fasta headers that contain multiple entries
        sep_ind = df_protein_names["Fasta headers"].str.contains(";")
        # replace all fasta headers with multiple entries with only the first one
        # TODO will there always be a fasta header?
        df_protein_names["Fasta headers"][sep_ind] = df_protein_names["Fasta headers"][sep_ind].str.split(";").apply(pd.Series)[0]
        # split the fasta headers with the pipe symbol
        fasta_col = df_protein_names["Fasta headers"].str.split("|", n=2).apply(pd.Series)
        fasta_col.columns = ["trash", "protein id", "description"]
        # extract the gene name from the description eg: "GN=abcd"
        gene_names_fasta = fasta_col["description"].str.extract(r"(GN=(.*?)(\s|$))")[1].apply(pd.Series)
        gene_names_fasta.columns = ["Gene name fasta"]
        # concat all important columns with the original dataframe
        df_protein_names = pd.concat([df_protein_names, fasta_col["protein id"], gene_names_fasta["Gene name fasta"]], axis=1)
        # add protein name from fasta description col
        df_protein_names["Protein name"] = fasta_col["description"].str.split("_", expand=True)[0]
        # filter all entries with duplicate Gene name fasta
        df_protein_names = df_protein_names.drop_duplicates(subset="Gene name fasta", keep=False)
        return df_protein_names, df_peptide_names

    def init_interest_from_xlsx(self) -> (dict, dict, dict):
        protein_path = os.path.join(self.path_pipeline_config, "important_protein_names.xlsx")
        receptor_path = os.path.join(self.path_pipeline_config, "important_receptor_names.xlsx")
        go_path = os.path.join(self.path_pipeline_config, "go_analysis_gene_names.xlsx")
        # make sure files exist
        if not os.path.isfile(protein_path):
            raise ValueError("missing important_protein_names.xlsx file")
        # make sure files exist
        if not os.path.isfile(receptor_path):
            raise ValueError("missing important_receptor_names.xlsx file")
        if not os.path.isfile(go_path):
            raise ValueError("missing go_analysis.xlsx file")

        def df_to_dict(df):
            return {col: df[col].dropna().tolist() for col in df}

        df_protein = pd.read_excel(protein_path)
        df_receptor = pd.read_excel(receptor_path)
        df_go = pd.read_excel(go_path)
        return df_to_dict(df_protein), df_to_dict(df_receptor), df_to_dict(df_go)

    def update_config_file(self):
        # store the config file as tmp
        yml_file_loc_tmp = os.path.join(self.path_config, self.yml_file_name_tmp)
        with open(yml_file_loc_tmp, "w") as outfile:
            self.yaml.dump(self.configs, outfile)

        # delete non tmp if exists
        yml_file_loc = os.path.join(self.path_config, self.yml_file_name)
        if self.yml_file_name in os.listdir(self.path_config):
            os.remove(yml_file_loc)

        # rename to non tmp
        os.rename(yml_file_loc_tmp, yml_file_loc)
