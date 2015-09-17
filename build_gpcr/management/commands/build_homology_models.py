from django.core.management.base import BaseCommand

from protein.models import Protein, ProteinSegment, ProteinConformation, ProteinAnomaly
from residue.models import Residue
from structure.models import Structure, PdbData, Rotamer
from common.alignment import Alignment, AlignedReferenceTemplate
import structure.structural_superposition as sp
import structure.assign_generic_numbers_gpcr as as_gn
from structure.calculate_RMSD import Validation

import Bio.PDB as PDB
from modeller import *
from modeller.automodel import *
from collections import OrderedDict
import os
import logging
import numpy as np
from io import StringIO
import sys
import pprint
from datetime import datetime
startTime = datetime.now()


class Command(BaseCommand):
    
    def handle(self, *args, **options):
        count=0
        s = [struct.protein_conformation.protein.parent.entry_name for struct in Structure.objects.all()]
        for protein in ProteinConformation.objects.all():
            if protein.protein.entry_name in s and count < 0:
                Homology_model = HomologyModeling(protein.protein.entry_name, 'Inactive', ['Inactive'])
                alignment = Homology_model.run_alignment()
                Homology_model.run_non_conserved_switcher(alignment)
    
                self.stdout.write(Homology_model.statistics, ending='')
                count+=1

        val = Validation()
#        print('7TM RMSD: ', val.PDB_RMSD("./structure/PDB/4XNW.pdb", "./structure/homology_models/P47900_Inactive/modeller_test.pdb",
#                            assign_gns=[1,2]))

#        print('7TM RMSD: ', val.PDB_RMSD("./structure/PDB/1U19.pdb", "./structure/homology_models/P02699_Inactive/modeller_test.pdb",
#                            assign_gns=[1,2]))
#        seq_nums1=[113,117,118,122,207,212,261,265,268,296]                    
#        print('binding pocket RMSD: ', val.PDB_RMSD("./structure/PDB/1U19.pdb", "./structure/homology_models/P02699_Inactive/modeller_test.pdb",
#                           assign_gns=[1,2], gn_list=['3x28', '3x32', '3x33', '3x37', '5x43', '5x47', '6x44', '6x48', '6x51', '7x43'], seq_nums1=[113,117,118,122,207,212,261,265,268,296], seq_nums2=[79,83,84,88,173,178,227,231,234,262]))

#        print('7TM RMSD: ', val.PDB_RMSD("./structure/PDB/4YAY.pdb", "./structure/homology_models/P30556_Inactive/modeller_test.pdb",
#                            assign_gns=[1,2]))
#        seq_nums1=[35, 77, 84, 88, 105, 108, 109, 112, 163, 285, 288, 292]
#        print('binding pocket RMSD: ', val.PDB_RMSD("./structure/PDB/4YAY.pdb", "./structure/homology_models/P30556_Inactive/modeller_test.pdb",
#                            assign_gns=[1,2], gn_list=['1x39', '2x53', '2x60', '2x64', '3x29', '3x32', '3x33', '3x36', '4x60', '7x35', '7x38', '7x42'], seq_nums1=[35, 77, 84, 88, 105, 108, 109, 112, 163, 285, 288, 292], seq_nums2=[9, 51, 58, 62, 79, 82, 83, 86, 137, 259, 262, 266]))
#                           
#        print('7TM RMSD: ', val.PDB_RMSD("./structure/PDB/4Z34.pdb", "./structure/homology_models/Q92633_Inactive/modeller_test.pdb",
#                            assign_gns=[1,2]))
#        seq_nums1=[52, 102, 124, 125, 128, 129, 132, 207, 210, 271, 274, 277, 278, 294, 296, 297]
#        print('binding pocket RMSD: ', val.PDB_RMSD("./structure/PDB/4Z34.pdb", "./structure/homology_models/Q92633_Inactive/modeller_test.pdb",
#                           assign_gns=[1,2], gn_list=['1x35', '2x57', '3x28', '3x29', '3x32', '3x33', '3x36', '5x40', '5x43', '6x48', '6x51', '6x54', '6x55', '7x35', '7x37', '7x38'], seq_nums1=[52, 102, 124, 125, 128, 129, 132, 207, 210, 271, 274, 277, 278, 294, 296, 297], seq_nums2=[7, 57, 79, 80, 83, 84, 87, 162, 165, 226, 229, 232, 233, 249, 251, 252]))
                
        Homology_model = HomologyModeling('gp132_human', 'Inactive', ['Inactive'])
        alignment = Homology_model.run_alignment()
        Homology_model.build_homology_model(alignment)#, switch_bulges=False, switch_constrictions=False, switch_rotamers=False)

        self.stdout.write(Homology_model.statistics, ending='')
        print(datetime.now() - startTime)

class HomologyModeling(object):
    ''' Class to build homology models for GPCRs. 
    
        @param reference_entry_name: str, protein entry name \n
        @param state: str, endogenous ligand state of reference \n
        @param query_states: list, list of endogenous ligand states to be applied for template search, 
        default: same as reference
    '''
    segment_coding = {1:'TM1',2:'TM2',3:'TM3',4:'TM4',5:'TM5',6:'TM6',7:'TM7'}
    def __init__(self, reference_entry_name, state, query_states):
        self.reference_entry_name = reference_entry_name
        self.state = state
        self.query_states = query_states
        self.statistics = CreateStatistics(self.reference_entry_name)
        self.reference_protein = Protein.objects.get(entry_name=self.reference_entry_name)
        self.uniprot_id = self.reference_protein.accession
        self.reference_sequence = self.reference_protein.sequence
        self.reference_class = self.reference_protein.family.parent.parent.parent
        self.statistics.add_info('uniprot_id',self.uniprot_id)
        self.segments = []
        self.similarity_table = OrderedDict()
        self.similarity_table_all = OrderedDict()
        self.main_structure = None
        self.main_template_preferred_chain = ''
        self.loop_template_table = OrderedDict()
        if os.path.isfile('./structure/homology_modeling.log'):
            os.remove('./structure/homology_modeling.log')
        logging.basicConfig(filename='./structure/homology_modeling.log',level=logging.WARNING)
        
    def __repr__(self):
        return "<{}, {}>".format(self.reference_entry_name, self.state)
   
    def run_alignment(self, core_alignment=True, query_states='default', 
                      segments=['TM1','TM2','TM3','TM4','TM5','TM6','TM7'], order_by='similarity'):
        ''' Creates pairwise alignment between reference and target receptor(s).
            Returns Alignment object.
            
            @param segments: list, list of segments to use, e.g.: ['TM1','IL1','TM2','EL1'] \n
            @param order_by: str, order results by identity, similarity or simscore
        '''
        if query_states=='default':
            query_states=self.query_states
        alignment = AlignedReferenceTemplate(self.reference_protein, segments, query_states, order_by)
        alignment.enhance_best_alignment()
        if core_alignment==True:
            self.segments = segments
            self.main_structure = alignment.main_template_structure
            self.similarity_table = alignment.similarity_table
            self.similarity_table_all = self.run_alignment(core_alignment=False, 
                                                           query_states=['Inactive','Active']).similarity_table
            self.main_template_preferred_chain = str(self.main_structure.preferred_chain)[0]
            self.statistics.add_info("main_template", self.main_structure)
            self.statistics.add_info("preferred_chain", self.main_template_preferred_chain)
            for loop in ['ICL1','ECL1','ICL2','ECL2','ICL3','ECL3']:
                loop_alignment = AlignedReferenceTemplate(self.reference_protein, [loop], ['Inactive','Active'], 
                                                          order_by='similarity', 
                                                          provide_main_template_structure=self.main_structure,
                                                          provide_similarity_table=self.similarity_table_all)
                self.loop_template_table[loop] = loop_alignment.loop_table
            self.statistics.add_info('similarity_table', self.similarity_table)
            self.statistics.add_info('loops',self.loop_template_table)           
        return alignment
        
    def build_homology_model(self, ref_temp_alignment, switch_bulges=True, switch_constrictions=True, loops=True, 
                             switch_rotamers=True):
        ''' Function to identify and switch non conserved residues in the alignment. Optionally,
            it can identify and switch bulge and constriction sites too. 
            
            @param ref_temp_alignment: AlignedReferenceAndTemplate, alignment of reference and main template with 
            alignment string. \n
            @param switch_bulges: boolean, identify and switch bulge sites. Default = True.
            @param switch_constrictions: boolean, identify and switch constriction sites. Default = True.
        '''
        a = ref_temp_alignment
        ref_bulge_list, temp_bulge_list, ref_const_list, temp_const_list = [],[],[],[]
        parse = GPCRDBParsingPDB()
        main_pdb_array = parse.pdb_array_creator(structure=self.main_structure)
        
        # loops
        if loops==True:
            loop_stat = OrderedDict()
            for label, structures in self.loop_template_table.items():
                loop = Loops(self.reference_protein, label, structures, self.main_structure)
                loop_template = loop.fetch_loop_residues()
                loop_insertion = loop.insert_loop_to_arrays(loop.loop_output_structure, main_pdb_array, loop_template, 
                                                            a.reference_dict, a.template_dict, a.alignment_dict)
                main_pdb_array = loop_insertion.main_pdb_array
                a.reference_dict = loop_insertion.reference_dict
                a.template_dict = loop_insertion.template_dict
                a.alignment_dict = loop_insertion.alignment_dict
                if loop.new_label!=None:
                    loop_stat[loop.new_label] = loop.loop_output_structure
                else:
                    loop_stat[label] = loop.loop_output_structure
            self.statistics.add_info('loops', loop_stat)

        # bulges and constrictions
        if switch_bulges==True or switch_constrictions==True:
            for ref_seg, temp_seg, aligned_seg in zip(a.reference_dict, a.template_dict, a.alignment_dict):
                for ref_res, temp_res, aligned_res in zip(a.reference_dict[ref_seg], a.template_dict[temp_seg], 
                                                          a.alignment_dict[aligned_seg]):
                    gn = ref_res
                    gn_TM = parse.gn_num_extract(gn, 'x')[0]
                    gn_num = parse.gn_num_extract(gn, 'x')[1]
                    
                    if a.alignment_dict[aligned_seg][aligned_res]=='-':
                        if (a.reference_dict[ref_seg][ref_res]=='-' and 
                            a.reference_dict[ref_seg][parse.gn_indecer(gn,'x',-1)] not in 
                            ['-','/'] and a.reference_dict[ref_seg][parse.gn_indecer(gn,'x',+1)] not in ['-','/']): 
        
                            # bulge in template
                            if len(str(gn_num))==3:
                                if switch_bulges==True:
                                    try:
                                        Bulge = Bulges(gn)
                                        bulge_template = Bulge.find_bulge_template(self.similarity_table_all, 
                                                                                   bulge_in_reference=False)
                                        bulge_site = parse.fetch_residues_from_pdb(self.main_structure,
                                                                                   [parse.gn_indecer(gn,'x',-2),
                                                                                    parse.gn_indecer(gn,'x',-1),gn,
                                                                                    parse.gn_indecer(gn,'x',+1),
                                                                                    parse.gn_indecer(gn,'x',+2)])
                                        superpose = sp.BulgeConstrictionSuperpose(bulge_site, bulge_template)
                                        new_residues = superpose.run()
                                        switch_res = 0
                                        for gen_num, atoms in bulge_template.items():
                                            if switch_res!=0 and switch_res!=3:
                                                gn__ = gen_num.replace('.','x')
                                                main_pdb_array[ref_seg][gen_num] = new_residues[gen_num]
                                                a.template_dict[temp_seg][gn__] = PDB.Polypeptide.three_to_one(
                                                                                   atoms[0].get_parent().get_resname())
                                                if a.template_dict[temp_seg][gn__]==a.reference_dict[ref_seg][gn__]:
                                                    a.alignment_dict[aligned_seg][gn__]=a.template_dict[temp_seg][gn__]
                                                else:
                                                    a.alignment_dict[aligned_seg][gn__]='.'
                                            switch_res+=1
                                        del main_pdb_array[ref_seg][gn.replace('x','.')]
                                        del a.reference_dict[ref_seg][gn]
                                        del a.template_dict[temp_seg][gn]
                                        del a.alignment_dict[aligned_seg][gn]
                                        temp_bulge_list.append({gn:Bulge.template})
                                    except:
                                        temp_bulge_list.append({gn:None})
                                    
                            # constriction in reference
                            else:
                                if switch_constrictions==True:
                                    try:
                                        Const = Constrictions(gn)
                                        constriction_template = Const.find_constriction_template(
                                                                                        self.similarity_table_all,
                                                                                        constriction_in_reference=True)
                                        constriction_site = OrderedDict([
                                            (parse.gn_indecer(gn,'x',-2).replace('x','.'), 
                                             main_pdb_array[ref_seg][parse.gn_indecer(gn,'x',-2).replace('x','.')]),
                                            (parse.gn_indecer(gn,'x',-1).replace('x','.'), 
                                             main_pdb_array[ref_seg][parse.gn_indecer(gn,'x',-1).replace('x','.')]),
                                            (gn.replace('x','.'), 
                                             main_pdb_array[ref_seg][parse.gn_indecer(gn,'x',-2).replace('x','.')]),
                                            (parse.gn_indecer(gn,'x',+1).replace('x','.'), 
                                             main_pdb_array[ref_seg][parse.gn_indecer(gn,'x',+1).replace('x','.')]),
                                            (parse.gn_indecer(gn,'x',+2).replace('x','.'), 
                                             main_pdb_array[ref_seg][parse.gn_indecer(gn,'x',+2).replace('x','.')])])
                                        superpose = sp.BulgeConstrictionSuperpose(constriction_site, 
                                                                                  constriction_template)
                                        new_residues = superpose.run()                                  
                                        switch_res = 0
                                        for gen_num, atoms in constriction_template.items():
                                            if switch_res!=0 and switch_res!=3:
                                                gn__ = gen_num.replace('.','x')
                                                main_pdb_array[ref_seg][gen_num] = new_residues[gen_num]
                                                a.template_dict[gn__] = PDB.Polypeptide.three_to_one(
                                                                                   atoms[0].get_parent().get_resname())
                                                if a.template_dict[temp_seg][gn__]==a.reference_dict[ref_seg][gn__]:
                                                    a.alignment_dict[aligned_seg][gn__]=a.template_dict[temp_seg][gn__]
                                            switch_res+=1
                                        ref_const_list.append({parse.gn_indecer(gn, 'x', -1)+'-'+parse.gn_indecer(gn, 
                                                                                             'x', +1):Const.template})
                                        del main_pdb_array[ref_seg][gn.replace('x','.')]
                                        del a.reference_dict[ref_seg][gn]
                                        del a.template_dict[temp_seg][gn]
                                        del a.alignment_dict[aligned_seg][gn]
                                    except:
                                        ref_const_list.append({parse.gn_indecer(gn, 'x', -1)+'-'+parse.gn_indecer(gn, 
                                                                                                    'x', +1):None})
                        elif (a.template_dict[ref_seg][temp_res]=='-' and 
                              a.template_dict[temp_seg][parse.gn_indecer(gn,'x',-1)] not in 
                              ['-','/'] and a.template_dict[temp_seg][parse.gn_indecer(gn,'x',+1)] not in ['-','/']): 
                            
                            # bulge in reference
                            if len(str(gn_num))==3:
                                if switch_bulges==True:
                                    try:
                                        Bulge = Bulges(gn)
                                        bulge_template = Bulge.find_bulge_template(self.similarity_table_all,
                                                                                   bulge_in_reference=True)
                                        bulge_site = parse.fetch_residues_from_pdb(self.main_structure,
                                                                                   [parse.gn_indecer(gn,'x',-2),
                                                                                    parse.gn_indecer(gn,'x',-1),
                                                                                    parse.gn_indecer(gn,'x',+1),
                                                                                    parse.gn_indecer(gn,'x',+2)])
                                        superpose = sp.BulgeConstrictionSuperpose(bulge_site, bulge_template)
                                        new_residues = superpose.run()
                                        switch_res = 0
                                        for gen_num, atoms in bulge_template.items():
                                            if switch_res!=0 and switch_res!=4:
                                                gn__ = gen_num.replace('.','x')
                                                main_pdb_array[ref_seg][gen_num] = new_residues[gen_num]
                                                a.template_dict[temp_seg][gn__] = PDB.Polypeptide.three_to_one(
                                                                                   atoms[0].get_parent().get_resname())
                                                if a.template_dict[temp_seg][gn__]==a.reference_dict[ref_seg][gn__]:
                                                    a.alignment_dict[aligned_seg][gn__]=a.template_dict[temp_seg][gn__]
                                            switch_res+=1
                                        ref_bulge_list.append({gn:Bulge.template})
                                    except:
                                        ref_bulge_list.append({gn:None})
                                    
                            # constriction in template
                            else:
                                if switch_constrictions==True:
                                    try:
                                        Const = Constrictions(gn)
                                        constriction_template = Const.find_constriction_template(
                                                                                       self.similarity_table_all,
                                                                                       constriction_in_reference=False)
                                        constriction_site = parse.fetch_residues_from_pdb(self.main_structure,
                                                                                          [parse.gn_indecer(gn,'x',-2),
                                                                                           parse.gn_indecer(gn,'x',-1),
                                                                                           parse.gn_indecer(gn,'x',+1),
                                                                                           parse.gn_indecer(gn,'x',+2)])
                                        superpose = sp.BulgeConstrictionSuperpose(constriction_site, 
                                                                                  constriction_template)
                                        new_residues = superpose.run()
                                        switch_res = 0
                                        for gen_num, atoms in constriction_template.items():
                                            if switch_res!=0 and switch_res!=4:
                                                gn__ = gen_num.replace('.','x')
                                                main_pdb_array[ref_seg][gen_num] = new_residues[gen_num]
                                                a.template_dict[temp_seg][gn__] = PDB.Polypeptide.three_to_one(
                                                                                   atoms[0].get_parent().get_resname())
                                                if a.template_dict[temp_seg][gn__]==a.reference_dict[ref_seg][gn__]:
                                                    a.alignment_dict[aligned_seg][gn__]=a.template_dict[temp_seg][gn__]
                                            switch_res+=1
                                        temp_const_list.append({parse.gn_indecer(gn, 'x', -1)+'-'+parse.gn_indecer(gn, 
                                                                                              'x', +1):Const.template})
                                    except:
                                        temp_const_list.append({parse.gn_indecer(gn, 'x', -1)+'-'+parse.gn_indecer(gn, 
                                                                                                    'x', +1):None})
            self.statistics.add_info('reference_bulges', ref_bulge_list)
            self.statistics.add_info('template_bulges', temp_bulge_list)
            self.statistics.add_info('reference_constrictions', ref_const_list)
            self.statistics.add_info('template_constrictions', temp_const_list)
            
            # insert bulge to array in the right place
            if ref_bulge_list!=[]:
                out_pdb_array = OrderedDict()
                bulge_gns = []
                for bulge in ref_bulge_list:
                    if list(bulge.values())[0]!=None:
                        gn = list(bulge.keys())[0].replace('x','.')
                        bulge_gns.append(gn)
                for seg_id, residues in main_pdb_array.items():
                    seg = OrderedDict()
                    for key, value in residues.items():
                        seg[key] = value                
                        if str(key)+'1' in bulge_gns:
                            seg[str(key)+'1'] = main_pdb_array[seg_id][str(key)+'1']
                    out_pdb_array[seg_id] = seg
                main_pdb_array = out_pdb_array
            
            if temp_const_list!=[]:
                out_pdb_array = OrderedDict()
                const_gns = []
                for const in temp_const_list:
                    if list(const.values())[0]!=None:
                        gn = parse.gn_indecer(list(const.keys())[0].split('-')[0].replace('x','.'), '.', +1)
                        const_gns.append(gn)
                for seg_id, residues in main_pdb_array.items():
                    seg = OrderedDict()
                    for key, value in residues.items():
                        seg[key] = value
                        if parse.gn_indecer(key, '.', +1) in const_gns:
                            seg[parse.gn_indecer(key, '.', +1)] = main_pdb_array[seg_id][parse.gn_indecer(key, '.', +1)]
                    out_pdb_array[seg_id] = seg
                main_pdb_array = out_pdb_array

        # check for inconsitencies with db
        pdb_db_inconsistencies = []
        for seg_label, segment in a.template_dict.items():
            try:
                for gn, res in segment.items():
                    try:
                        if res==PDB.Polypeptide.three_to_one(
                                            main_pdb_array[seg_label][gn.replace('x','.')][0].get_parent().get_resname()):
                            pass
                        elif 'x' in gn:
                            pdb_db_inconsistencies.append({gn:a.template_dict[seg_label][gn]})
                    except:
                        pass
            except:
                pass
        if pdb_db_inconsistencies!=[]:
            for incons in pdb_db_inconsistencies:
                seg = self.segment_coding[int(list(incons.keys())[0][0])]
                seq_num = Residue.objects.get(
                                        protein_conformation__protein=self.main_structure.protein_conformation.protein, 
                                        generic_number__label=list(incons.keys())[0])
                temp_segment, temp_array = OrderedDict(), OrderedDict()
                for key, value in main_pdb_array[seg].items():
                    if key==str(seq_num.sequence_number):
                        temp_segment[list(incons.keys())[0].replace('x','.')] = value
                    else:
                        temp_segment[key] = value
                for seg_id, segment in main_pdb_array.items():
                    if seg_id==seg:
                        temp_array[seg_id] = temp_segment
                    else:
                        temp_array[seg_id] = segment
                main_pdb_array = temp_array
                a.template_dict[seg][list(incons.keys())[0]] = PDB.Polypeptide.three_to_one(
                            main_pdb_array[seg][list(incons.keys())[0].replace('x','.')][0].get_parent().get_resname())
                if a.reference_dict[seg][list(incons.keys())[0]]==a.template_dict[seg][list(incons.keys())[0]]:
                    a.alignment_dict[seg][list(incons.keys())[0]] = a.reference_dict[seg][list(incons.keys())[0]]
                    
        self.statistics.add_info('pdb_db_inconsistencies', pdb_db_inconsistencies)
        path = "./structure/homology_models/{}_{}/".format(self.uniprot_id,self.state)
        if not os.path.exists(path):
            os.mkdir(path)
        self.write_homology_model_pdb(
                                "./structure/homology_models/{}_{}/pre_switch.pdb".format(self.uniprot_id, self.state), 
                                main_pdb_array, a)        
        
        # inserting loops for free modeling
        for label, template in loop_stat.items():
            if template==None:
                modeling_loops = Loops(self.reference_protein, label, self.similarity_table_all, self.main_structure)
                modeling_loops.insert_gaps_for_loops_to_arrays(main_pdb_array, a.reference_dict, a.template_dict,
                                                               a.alignment_dict)
                main_pdb_array = modeling_loops.main_pdb_array
                a.reference_dict = modeling_loops.reference_dict
                a.template_dict = modeling_loops.template_dict
                a.alignment_dict = modeling_loops.alignment_dict
        
        # non-conserved residue switching
        if switch_rotamers==True:
            non_cons_switch = self.run_non_conserved_switcher(main_pdb_array,a.reference_dict,a.template_dict,
                                                              a.alignment_dict)
            main_pdb_array = non_cons_switch[0]
            a.reference_dict = non_cons_switch[1]
            a.template_dict = non_cons_switch[2]
            a.alignment_dict = non_cons_switch[3]
            trimmed_residues = non_cons_switch[4]
        else:
            trimmed_residues=[]
            for seg_id, seg in main_pdb_array.items():
                for key in seg:
                    if a.reference_dict[seg_id][str(key).replace('.','x')]!='-':
                        trimmed_residues.append(key)

        # write to file
        path = "./structure/homology_models/{}_{}/".format(self.uniprot_id,self.state)
        if not os.path.exists(path):
            os.mkdir(path)
        trimmed_res_nums = self.write_homology_model_pdb(path+self.uniprot_id+"_post.pdb", main_pdb_array, 
                                                         a, trimmed_residues=trimmed_residues)
        # Model with MODELLER
#        self.create_PIR_file(a, path+self.uniprot_id+"_post.pdb")
#        self.run_MODELLER("./structure/PIR/"+self.uniprot_id+"_"+self.state+".pir", path+self.uniprot_id+"_post.pdb", 
#                          self.uniprot_id, 1, "modeller_test.pdb", atom_dict=trimmed_res_nums)
#        
#        with open('./structure/homology_models/{}_Inactive/{}.stat.txt'.format(self.uniprot_id, self.uniprot_id), 'w') as stat_file:
#            for label, info in self.statistics.items():
#                stat_file.write('{} : {}\n'.format(label, info))
        return a       
    
    def run_non_conserved_switcher(self, main_pdb_array, reference_dict, template_dict, alignment_dict):
        ''' Switches non-conserved residues with best possible template. Returns refreshed main_pdb_array 
            (atom coordinates), reference_dict (reference generic numbers and residue ids), template_dict (template 
            generic numbers and residue ids) and alignment_dict (aligned reference and template dictionary). 
            
            @param main_pdb_array: nested OrderedDict(), output of GPCRDBParsingPDB().pdb_array_creator()
            @param reference_dict: reference dictionary of AlignedReferenceTemplate.
            @param template_dict: template dictionary of AlignedReferenceTemplate.
            @param alignment_dict: alignment dictionary of AlignedReferenceTemplate.
        '''
        parse = GPCRDBParsingPDB()
        ref_length = 0
        conserved_count = 0
        non_cons_count = 0
        trimmed_res_num = 0
        switched_count = 0
        non_cons_res_templates, conserved_residues = OrderedDict(), OrderedDict()
        trimmed_residues = []
        res_list = []
        for ref_seg, temp_seg, aligned_seg in zip(reference_dict, template_dict, alignment_dict):
            for ref_res, temp_res, aligned_res in zip(reference_dict[ref_seg], template_dict[temp_seg], 
                                                      alignment_dict[aligned_seg]):
                if reference_dict[ref_seg][ref_res]!='-' and reference_dict[ref_seg][ref_res]!='/':
                    ref_length+=1
                if (alignment_dict[aligned_seg][aligned_res]!='.' and
                    alignment_dict[aligned_seg][aligned_res]!='x' and 
                    alignment_dict[aligned_seg][aligned_res]!='-'):
                    conserved_count+=1
                    conserved_residues[ref_res] = alignment_dict[aligned_seg][aligned_res]
                
                gn = ref_res
    
                if (alignment_dict[aligned_seg][aligned_res]=='.' and 
                    reference_dict[ref_seg][gn]!=template_dict[temp_seg][gn]) and reference_dict[ref_seg][gn]!='x':
                    non_cons_count+=1
                    try:
                        residues = Residue.objects.filter(generic_number__label=ref_res)
                        proteins_w_this_gn = [res.protein_conformation.protein.parent for res in 
                                                residues if str(res.amino_acid)==reference_dict[ref_seg][ref_res]]
                        proteins_w_this_gn = list(set(proteins_w_this_gn))
                    except:
                        proteins_w_this_gn = []
                    gn_ = str(ref_res).replace('x','.')
                    no_match = True
                    for struct in self.similarity_table:
                        if struct.protein_conformation.protein.parent in proteins_w_this_gn:
                            try:
                                alt_temp = parse.fetch_residues_from_pdb(struct, [gn])
                                if reference_dict[ref_seg][gn]==PDB.Polypeptide.three_to_one(
                                                                        alt_temp[gn_][0].get_parent().get_resname()):
                                    orig_res = main_pdb_array[ref_seg][gn_]
                                    alt_res = parse.fetch_residues_from_pdb(struct,[gn])[gn_]
                                    superpose = sp.RotamerSuperpose(orig_res, alt_res)
                                    new_atoms = superpose.run()
                                    if superpose.backbone_rmsd>0.3:
                                        continue
                                    main_pdb_array[ref_seg][gn_] = new_atoms
                                    template_dict[temp_seg][gn] = reference_dict[ref_seg][gn]
                                    switched_count+=1                     
                                    non_cons_res_templates[ref_res] = struct
                                    res=Residue.objects.get(protein_conformation__protein=self.reference_protein, generic_number__label=ref_res)
                                    res_list.append(res.sequence_number)
                                    no_match = False
                                    break
                            except:
                                pass
                    if no_match==True:
                        try:
                            if 'free' not in ref_seg:
                                residue = main_pdb_array[ref_seg][gn_]
                                main_pdb_array[ref_seg][gn_] = residue[0:5]
                                trimmed_residues.append(gn_)
                                trimmed_res_num+=1
                            elif 'free' in ref_seg:
                                trimmed_residues.append(gn_)
                                trimmed_res_num+=1
                        except:
                            logging.warning("Missing atoms in {} at {}".format(self.main_structure,gn))

        self.statistics.add_info('ref_seq_length', ref_length)
        self.statistics.add_info('conserved_num', conserved_count)
        self.statistics.add_info('non_conserved_num', non_cons_count)
        self.statistics.add_info('trimmed_residues_num', trimmed_res_num)
        self.statistics.add_info('non_conserved_switched_num', switched_count)
        self.statistics.add_info('conserved_residues', conserved_residues)
        self.statistics.add_info('non_conserved_residue_templates', non_cons_res_templates)
        self.statistics.add_info('trimmed_residues', trimmed_residues)

        return [main_pdb_array, reference_dict, template_dict, alignment_dict, trimmed_residues]
    
    def write_homology_model_pdb(self, filename, main_pdb_array, ref_temp_alignment, trimmed_residues=[]):
        ''' Write PDB file from pdb array to file.
        
            @param filename: str, filename of output file \n
            @param main_pdb_array: OrderedDict(), of atoms of pdb, where keys are generic numbers/residue numbers and
            values are list of atoms. Output of GPCRDBParsingPDB.pdb_array_creator().
            @param ref_temp_alignment: AlignedReferenceAndTemplate, only writes residues that are in ref_temp_alignment.
        '''
        key = ''
#        self.starting_res_num = list(Residue.objects.filter(protein_segment=2, protein_conformation__protein=self.reference_protein))[0].sequence_number
#        res_num = self.starting_res_num-1
        res_num = 0
        atom_num = 0
        trimmed_resi_nums = OrderedDict()
        with open(filename,'w+') as f:
            for seg_id, segment in main_pdb_array.items():
                trimmed_segment = OrderedDict()
                for key in segment:
                    if str(key).replace('.','x') :#in ref_temp_alignment.reference_dict[seg_id]:
                        res_num+=1
                        if key in trimmed_residues:
                            trimmed_segment[key] = res_num
                            if 'x' in segment[key]:
                                f.write("\nTER")
                            if '?' in key:
                                continue
                        if 'x' in segment[key]:
                            f.write("\nTER")
                            continue
                        for atom in main_pdb_array[seg_id][key]: 
                            atom_num+=1
                            coord = list(atom.get_coord())
                            coord1 = "%8.3f"% (coord[0])
                            coord2 = "%8.3f"% (coord[1])
                            coord3 = "%8.3f"% (coord[2])
                            if str(atom.get_id())=='CA':
                                if len(key)==4:
                                    bfact = "%6.2f"% (float(key))
                                elif '.' not in key:
                                    bfact = "%6.2f"% (float(atom.get_bfactor()))
                                else:
                                    bfact = " -%4.2f"% (float(key))
                            else:
                                bfact = "%6.2f"% (float(atom.get_bfactor()))
                            occupancy = "%6.2f"% (atom.get_occupancy())
                            template="""
ATOM{atom_num}  {atom}{res} {chain}{res_num}{coord1}{coord2}{coord3}{occupancy}{bfactor}{atom_s}  """
                            context={"atom_num":str(atom_num).rjust(7), "atom":str(atom.get_id()).ljust(4),
                                     "res":atom.get_parent().get_resname(), 
                                     "chain":str(self.main_template_preferred_chain)[0],
                                     "res_num":str(res_num).rjust(4), "coord1":coord1.rjust(12), 
                                     "coord2":coord2.rjust(8), "coord3":coord3.rjust(8), 
                                     "occupancy":str(occupancy).rjust(3),
                                     "bfactor":str(bfact).rjust(4), "atom_s":str(str(atom.get_id())[0]).rjust(12)}
                            f.write(template.format(**context))
                trimmed_resi_nums[seg_id] = trimmed_segment
            f.write("\nTER\nEND")
        return trimmed_resi_nums
                    
    def create_PIR_file(self, ref_temp_alignment, template_file):
        ''' Create PIR file from reference and template alignment (AlignedReferenceAndTemplate).
        
            @param ref_temp_alignment: AlignedReferenceAndTemplate
            @template_file: str, name of template file with path
        '''
        ref_sequence, temp_sequence = '',''
        res_num = 0
        for ref_seg, temp_seg in zip(ref_temp_alignment.reference_dict, ref_temp_alignment.template_dict):
            for ref_res, temp_res in zip(ref_temp_alignment.reference_dict[ref_seg], 
                                         ref_temp_alignment.template_dict[temp_seg]):
                res_num+=1
                if ref_temp_alignment.reference_dict[ref_seg][ref_res]=='x':
                    ref_sequence+='-'
                else:
                    ref_sequence+=ref_temp_alignment.reference_dict[ref_seg][ref_res]
                if ref_temp_alignment.template_dict[temp_seg][temp_res]=='x':
                    temp_sequence+='-'
                else:
                    temp_sequence+=ref_temp_alignment.template_dict[temp_seg][temp_res]
        with open("./structure/PIR/"+self.uniprot_id+"_"+self.state+".pir", 'w+') as output_file:
            template="""
>P1;{temp_file}
structure:{temp_file}:1:{chain}:{res_num}:{chain}::::
{temp_sequence}*

>P1;{uniprot}
sequence:{uniprot}::::::::
{ref_sequence}*
            """
            context={"temp_file":template_file,
                     "chain":self.main_template_preferred_chain,
                     "res_num":res_num,
                     "temp_sequence":temp_sequence,
                     "uniprot":self.uniprot_id,
                     "ref_sequence":ref_sequence}
            output_file.write(template.format(**context))
            
    def run_MODELLER(self, pir_file, template, reference, number_of_models, output_file_name, atom_dict=None):
        ''' Build homology model with MODELLER.
        
            @param pir_file: str, file name of PIR file with path \n
            @param template: str, file name of template with path \n
            @param reference: str, Uniprot code of reference sequence \n
            @param number_of_models: int, number of models to be built \n
            @param output_file_name: str, name of output file
        '''
#        log.verbose()
        env = environ(rand_seed=80851) #!!random number generator
        
        if atom_dict==None:
            a = automodel(env, alnfile = pir_file, knowns = template, sequence = reference, 
                          assess_methods=(assess.DOPE, assess.GA341))
        else:
            a = HomologyMODELLER(env, alnfile = pir_file, knowns = template, sequence = reference, 
                                 assess_methods=(assess.DOPE, assess.GA341), atom_selection=atom_dict)
        a.starting_model = 1
        a.ending_model = number_of_models
        a.md_level = refine.very_slow
        path = "./structure/homology_models/{}".format(reference+"_"+self.state)
        if not os.path.exists(path):
            os.mkdir(path)
        a.make()
        
        # Get a list of all successfully built models from a.outputs
        ok_models = [x for x in a.outputs if x['failure'] is None]

        # Rank the models by DOPE score
        key = 'DOPE score'
        if sys.version_info[:2] == (2,3):
            # Python 2.3's sort doesn't have a 'key' argument
            ok_models.sort(lambda a,b: cmp(a[key], b[key]))
        else:
            ok_models.sort(key=lambda a: a[key])
        
        # Get top model
        m = ok_models[0]
        print("Top model: %s (DOPE score %.3f)" % (m['name'], m[key]))        
        
        for file in os.listdir("./"):
            if file==m['name']:
                os.rename("./"+file, "./structure/homology_models/{}_{}/".format(self.uniprot_id,
                                                                                 self.state)+output_file_name)
            elif file.startswith(self.uniprot_id):
                os.remove("./"+file)#, "./structure/homology_models/{}_{}/".format(self.uniprot_id,self.state)+file)
            
class HomologyMODELLER(automodel):
    def __init__(self, env, alnfile, knowns, sequence, assess_methods, atom_selection):
        super(HomologyMODELLER, self).__init__(env, alnfile=alnfile, knowns=knowns, sequence=sequence, 
                                               assess_methods=assess_methods)
        self.atom_dict = atom_selection
        
    def select_atoms(self):
        selection_out = []
        for seg_id, segment in self.atom_dict.items():
            for gn, atom in segment.items():
                selection_out.append(self.residues[str(atom)])
        return selection(selection_out)

class Loops(object):
    ''' Class to handle loops in GPCR structures.
    '''
    def __init__(self, reference_protein, loop_label, loop_template_structures, main_structure):
        self.segment_order = {'TM1':1, 'ICL1':1.5, 'TM2':2, 'ECL1':2.5, 'TM3':3, 'ICL2':3.5, 'TM4':4, 'ECL2':4.5, 
                              'TM5':5, 'ICL3':5.5, 'TM6':6, 'ECL3':6.5, 'TM7':7}
        self.reference_protein = reference_protein
        self.loop_label = loop_label
        self.loop_template_structures = loop_template_structures
        self.main_structure = main_structure
        self.loop_output_structure = None
        self.new_label = None
    
    def fetch_loop_residues(self):
        ''' Fetch list of Atom objects of the loop when there is an available template. Returns an OrderedDict().
        '''
        if self.loop_template_structures!=None:
            parse = GPCRDBParsingPDB()
            for template in self.loop_template_structures:
                try:
                    output = OrderedDict()
                    loop_residues = Residue.objects.filter(protein_segment__slug=self.loop_label, 
                                                           protein_conformation=template.protein_conformation,
                                                           generic_number__isnull=True)
                    b_num = loop_residues[0].sequence_number
                    a_num = loop_residues.reverse()[0].sequence_number
                    segment = loop_residues[0].protein_segment
                    before8 = Residue.objects.filter(protein_conformation=template.protein_conformation, 
                                                     sequence_number__in=[b_num-1,b_num-2,b_num-3,b_num-4,
                                                                          b_num-5,b_num-6,b_num-7,b_num-8])
                    after8 = Residue.objects.filter(protein_conformation=template.protein_conformation, 
                                                     sequence_number__in=[a_num+1,a_num+2,a_num+3,a_num+4,
                                                                          a_num+5,a_num+6,a_num+7,a_num+8])
                    before_gns = [x.generic_number.label for x in before8]
                    mid_nums = [x.sequence_number for x in loop_residues]
                    after_gns = [x.generic_number.label for x in after8]
                    alt_residues_temp = parse.fetch_residues_from_pdb(template, before_gns+mid_nums+after_gns)
                    alt_residues = OrderedDict()
                    for id_, atoms in alt_residues_temp.items():
                        if '.' not in str(id_):
                            alt_residues[str(id_)] = atoms
                        else:
                            alt_residues[id_] = atoms
                    if template==self.main_structure:
                        key_list = list(alt_residues.keys())[7:-7]
                        for key in key_list:
                            output[key] = alt_residues[key]
                        self.loop_output_structure = self.main_structure
                        return output
                    orig_before_residues = Residue.objects.filter(
                                                protein_conformation=self.main_structure.protein_conformation, 
                                                protein_segment__id=segment.id-1)
                    orig_after_residues = Residue.objects.filter(
                                                protein_conformation=self.main_structure.protein_conformation, 
                                                protein_segment__id=segment.id+1)
                    orig_before_gns = []
                    orig_after_gns = []
                    for res in orig_before_residues.reverse():
                        if len(orig_before_gns)<8:
                            orig_before_gns.append(res.generic_number.label)
                    for res in orig_after_residues:
                        if len(orig_after_gns)<8:
                            orig_after_gns.append(res.generic_number.label)
                    orig_before_gns = list(reversed(orig_before_gns))
                    if before_gns!=orig_before_gns or after_gns!=orig_after_gns:
                        continue
                    orig_residues = parse.fetch_residues_from_pdb(self.main_structure, 
                                                                  orig_before_gns+orig_after_gns)
                    superpose = sp.LoopSuperpose(orig_residues, alt_residues)
                    new_residues = superpose.run()
                    key_list = list(new_residues.keys())[7:-7]
                    for key in key_list:
                        output[key] = new_residues[key]
                    self.loop_output_structure = template
                    return output
                except:
                    return None
        else:
            return None
                    
    def insert_loop_to_arrays(self, loop_output_structure, main_pdb_array, loop_template, reference_dict, 
                              template_dict, alignment_dict):
        ''' Updates the homology model with loop segments. Inserts previously fetched lists of loop Atom objects to 
            the proper arrays, dictionaries.
            
            @param loop_output_structure: Structure object of loop template.
            @param main_pdb_array: nested OrderedDict(), output of GPCRDBParsingPDB().pdb_array_creator().
            @param loop_template: OrderedDict() of loop template with lists of Atom objects as values.
            @param reference_dict: reference dictionary of AlignedReferenceTemplate.
            @param template_dict: template dictionary of AlignedReferenceTemplate.
            @param alignment_dict: alignment dictionary of AlignedReferenceTemplate.
        '''
        temp_array = OrderedDict()
        temp_loop = OrderedDict()
        if loop_template!=None and loop_output_structure!=self.main_structure:
            loop_keys = list(loop_template.keys())[2:-2]
            continuous_loop = False
            for seg_label, gns in main_pdb_array.items():
                if self.segment_order[self.loop_label]-self.segment_order[seg_label[:4]]==0.5:
                    temp_array[seg_label] = gns
                    l_res = 1
                    temp_loop[self.loop_label+'?'+'1'] = 'x'
                    for key in loop_keys:
                        l_res+=1
                        temp_loop[self.loop_label+'|'+str(l_res)] = loop_template[key]
                    temp_loop[self.loop_label+'?'+str(l_res+1)] = 'x'
                    temp_array[self.loop_label+'_dis'] = temp_loop
                else:
                    temp_array[seg_label] = gns
            self.main_pdb_array = temp_array
            
        elif loop_template!=None and loop_output_structure==self.main_structure:
            loop_keys = list(loop_template.keys())[1:-1]
            continuous_loop = True
            for seg_label, gns in main_pdb_array.items():
                if self.segment_order[self.loop_label]-self.segment_order[seg_label[:4]]==0.5:
                    temp_array[seg_label] = gns
                    l_res = 0
                    for key in loop_keys:
                        l_res+=1
                        temp_loop[self.loop_label+'|'+str(l_res)] = loop_template[key]
                    temp_array[self.loop_label+'_cont'] = temp_loop
                else:
                    temp_array[seg_label] = gns
            self.main_pdb_array = temp_array          
        else:
            self.main_pdb_array = main_pdb_array
        if loop_template!=None:
            temp_ref_dict, temp_temp_dict, temp_aligned_dict = OrderedDict(),OrderedDict(),OrderedDict()
            ref_residues = list(Residue.objects.filter(protein_conformation__protein=self.reference_protein, 
                                                  protein_segment__slug=self.loop_label))
            for ref_seg, temp_seg, aligned_seg in zip(reference_dict, template_dict, alignment_dict):
                if ref_seg[0]=='T' and ref_seg[-1]==list(loop_template.keys())[0][0]:
                    temp_ref_dict[ref_seg] = reference_dict[ref_seg]
                    temp_temp_dict[temp_seg] = template_dict[temp_seg]
                    temp_aligned_dict[aligned_seg] = alignment_dict[aligned_seg]
                    input_residues = list(loop_template.keys())[1:-1]
                    ref_loop_seg, temp_loop_seg, aligned_loop_seg = OrderedDict(),OrderedDict(),OrderedDict()
                    if continuous_loop==True:
                        l_res=0
                        for r_res, r_id in zip(ref_residues, input_residues):
                            l_res+=1
                            ref_loop_seg[self.loop_label+'|'+str(l_res)] = r_res.amino_acid
                            temp_loop_seg[self.loop_label+'|'+str(l_res)] = PDB.Polypeptide.three_to_one(loop_template[r_id][0].get_parent().get_resname())
                            if ref_loop_seg[self.loop_label+'|'+str(l_res)]==temp_loop_seg[self.loop_label+'|'+str(l_res)]:                        
                                aligned_loop_seg[self.loop_label+'|'+str(l_res)] = ref_loop_seg[self.loop_label+'|'+str(l_res)]
                            else:
                                aligned_loop_seg[self.loop_label+'|'+str(l_res)] = '.'    
                        self.new_label = self.loop_label+'_cont'
                        temp_ref_dict[self.loop_label+'_cont'] = ref_loop_seg
                        temp_temp_dict[self.loop_label+'_cont'] = temp_loop_seg
                        temp_aligned_dict[self.loop_label+'_cont'] = aligned_loop_seg
                    else:
                        l_res=1
                        ref_loop_seg[self.loop_label+'?'+'1'] = ref_residues[0].amino_acid
                        temp_loop_seg[self.loop_label+'?'+'1'] = 'x'
                        aligned_loop_seg[self.loop_label+'?'+'1'] = '.'
                        for r_res, r_id in zip(ref_residues[1:-1], input_residues[1:-1]):
                            l_res+=1
                            ref_loop_seg[self.loop_label+'|'+str(l_res)] = r_res.amino_acid
                            temp_loop_seg[self.loop_label+'|'+str(l_res)] = PDB.Polypeptide.three_to_one(loop_template[r_id][0].get_parent().get_resname())
                            if ref_loop_seg[self.loop_label+'|'+str(l_res)]==temp_loop_seg[self.loop_label+'|'+str(l_res)]:                        
                                aligned_loop_seg[self.loop_label+'|'+str(l_res)] = ref_loop_seg[self.loop_label+'|'+str(l_res)]
                            else:
                                aligned_loop_seg[self.loop_label+'|'+str(l_res)] = '.'
                        ref_loop_seg[self.loop_label+'?'+str(l_res+1)] = ref_residues[-1].amino_acid
                        temp_loop_seg[self.loop_label+'?'+str(l_res+1)] = 'x'
                        aligned_loop_seg[self.loop_label+'?'+str(l_res+1)] = '.'
                        self.new_label = self.loop_label+'_dis'
                        temp_ref_dict[self.loop_label+'_dis'] = ref_loop_seg
                        temp_temp_dict[self.loop_label+'_dis'] = temp_loop_seg
                        temp_aligned_dict[self.loop_label+'_dis'] = aligned_loop_seg
                else:
                    temp_ref_dict[ref_seg] = reference_dict[ref_seg]
                    temp_temp_dict[temp_seg] = template_dict[temp_seg]
                    temp_aligned_dict[aligned_seg] = alignment_dict[aligned_seg]
            self.reference_dict = temp_ref_dict
            self.template_dict = temp_temp_dict
            self.alignment_dict = temp_aligned_dict
        else:
            self.reference_dict = reference_dict
            self.template_dict = template_dict
            self.alignment_dict = alignment_dict
        return self
            
    def insert_gaps_for_loops_to_arrays(self, main_pdb_array, reference_dict, template_dict, alignment_dict):
        ''' When there is no template for a loop region, this function inserts gaps for that region into the main 
            template, fetches the reference residues and inserts these into the arrays. This allows for Modeller to
            freely model these loop regions.
            
            @param main_pdb_array: nested OrderedDict(), output of GPCRDBParsingPDB().pdb_array_creator().
            @param reference_dict: reference dictionary of AlignedReferenceTemplate.
            @param template_dict: template dictionary of AlignedReferenceTemplate.
            @param alignment_dict: alignment dictionary of AlignedReferenceTemplate.
        '''
        residues = Residue.objects.filter(protein_conformation__protein=self.reference_protein, 
                                          protein_segment__slug=self.loop_label)
        temp_pdb_array = OrderedDict()
        for seg_id, seg in main_pdb_array.items():
            if self.segment_order[self.loop_label]-self.segment_order[seg_id[:4]]==0.5:
                temp_loop = OrderedDict()
                count=0
                temp_pdb_array[seg_id] = seg
                for r in residues:
                    count+=1
                    temp_loop[self.loop_label+'?'+str(count)] = '-'
                temp_pdb_array[self.loop_label+'_free'] = temp_loop
                self.new_label = self.loop_label+'_free'
            else:
                temp_pdb_array[seg_id] = seg
        self.main_pdb_array = temp_pdb_array
        temp_ref_dict, temp_temp_dict, temp_aligned_dict = OrderedDict(), OrderedDict(), OrderedDict()
        for ref_seg, temp_seg, aligned_seg in zip(reference_dict, template_dict, alignment_dict):
            if self.segment_order[self.loop_label]-self.segment_order[ref_seg[:4]]==0.5:
                temp_ref_loop, temp_temp_loop, temp_aligned_loop = OrderedDict(), OrderedDict(), OrderedDict()
                temp_ref_dict[ref_seg] = reference_dict[ref_seg]
                temp_temp_dict[temp_seg] = template_dict[temp_seg]
                temp_aligned_dict[aligned_seg] = alignment_dict[aligned_seg]
                count=0
                for r in residues:
                    count+=1
                    temp_ref_loop[self.loop_label+'?'+str(count)] = r.amino_acid
                    temp_temp_loop[self.loop_label+'?'+str(count)] = '-'
                    temp_aligned_loop[self.loop_label+'?'+str(count)] = '.'
                temp_ref_dict[self.loop_label+'_free'] = temp_ref_loop
                temp_temp_dict[self.loop_label+'_free'] = temp_temp_loop
                temp_aligned_dict[self.loop_label+'_free'] = temp_aligned_loop
            else:
                temp_ref_dict[ref_seg] = reference_dict[ref_seg]
                temp_temp_dict[temp_seg] = template_dict[temp_seg]
                temp_aligned_dict[aligned_seg] = alignment_dict[aligned_seg]
        self.reference_dict = temp_ref_dict
        self.template_dict = temp_temp_dict
        self.alignment_dict = temp_aligned_dict

class Bulges(object):
    ''' Class to handle bulges in GPCR structures.
    '''
    def __init__(self, gn):
        self.gn = gn
        self.bulge_templates = []
        self.template = None
    
    def find_bulge_template(self, similarity_table, bulge_in_reference):
        ''' Searches for bulge template, returns residues of template (5 residues if the bulge is in the reference, 4
            residues if the bulge is in the template). 
            
            @param gn: str, Generic number of bulge, e.g. 1x411 \n
            @param similarity_table: OrderedDict(), table of structures ordered by preference.
            Output of HomologyModeling().create_similarity_table(). \n
            @param bulge_in_reference: boolean, Set it to True if the bulge is in the reference, set it to False if the
            bulge is in the template.
        '''
        gn = self.gn
        parse = GPCRDBParsingPDB()
        if bulge_in_reference==True:
            matches = Residue.objects.filter(generic_number__label=gn)
        elif bulge_in_reference==False:
            excludees = Residue.objects.filter(generic_number__label=gn)
            excludee_proteins = list(OrderedDict.fromkeys([res.protein_conformation.protein.parent.entry_name 
                                        for res in excludees if res.protein_conformation.protein.parent!=None]))
            matches = Residue.objects.filter(generic_number__label=gn[:-1])
        for structure, value in similarity_table.items():  
            protein_object = Protein.objects.get(id=structure.protein_conformation.protein.parent.id)
            this_anomaly = ProteinAnomaly.objects.get(generic_number__label=gn)
            if this_anomaly in structure.protein_anomalies.all():
                print(structure, gn)
            try:                            
                for match in matches:
                    if bulge_in_reference==True:
                        if match.protein_conformation.protein.parent==protein_object:
                            self.bulge_templates.append(structure)
                    elif bulge_in_reference==False:
                        if (match.protein_conformation.protein.parent==protein_object and 
                            match.protein_conformation.protein.parent.entry_name not in excludee_proteins):
                            self.bulge_templates.append(structure)
            except:
                pass
        mod_bulge = False
        for temp in self.bulge_templates:
            try:
                if bulge_in_reference==True:
                    alt_bulge = parse.fetch_residues_from_pdb(temp, 
                                                              [parse.gn_indecer(gn,'x',-2),
                                                               parse.gn_indecer(gn,'x',-1),gn,
                                                               parse.gn_indecer(gn,'x',+1),
                                                               parse.gn_indecer(gn,'x',+2)])
                elif bulge_in_reference==False:
                    gn_list = [parse.gn_indecer(gn,'x',-2), parse.gn_indecer(gn,'x',-1),
                               parse.gn_indecer(gn,'x',+1), parse.gn_indecer(gn,'x',+2)]
                    for gn_ in gn_list:
                        if len(Residue.objects.filter(generic_number__label=gn_+'1').filter(
                                                                    protein_conformation=temp.protein_conformation))>0:
                            if int(gn[:-1].split('x')[1])-int(gn_.split('x')[1])==1:
                                gn_list[0] = gn_+'1'
                            elif int(gn[:-1].split('x')[1])-int(gn_.split('x')[1])==-1:
                                gn_list[2] = gn_+'1'
                                gn_list[3] = parse.gn_indecer(gn_,'x',+1)
                            elif int(gn[:-1].split('x')[1])-int(gn_.split('x')[1])==-2:
                                gn_list[3] = gn_+'1'
                            mod_bulge = True
                    if mod_bulge==True:
                        alt_bulge = parse.fetch_residues_from_pdb(temp, gn_list, modify_bulges=True)
                    else:
                        alt_bulge = parse.fetch_residues_from_pdb(temp, gn_list)
                self.template = temp              
                break
            except:
                self.template = None               
        return alt_bulge
            
class Constrictions(object):
    ''' Class to handle constrictions in GPCRs.
    '''
    def __init__(self, gn):
        self.gn = gn
        self.constriction_templates = []
        self.template = None
    
    def find_constriction_template(self, similarity_table, constriction_in_reference):
        ''' Searches for constriction template, returns residues of template (4 residues if the constriction is in the 
            reference, 5 residues if the constriction is in the template). 
            
            @param gn: str, Generic number of constriction, e.g. 7x44 \n
            @param similarity_table: OrderedDict(), table of structures ordered by preference.
            Output of HomologyModeling().create_similarity_table(). \n
            @param constriction_in_reference: boolean, Set it to True if the constriction is in the reference, set it 
            to False if the constriction is in the template.
        '''
        gn = self.gn
        parse = GPCRDBParsingPDB()
        if constriction_in_reference==True:
            excludees = Residue.objects.filter(generic_number__label=gn)
            excludee_proteins = list(OrderedDict.fromkeys([res.protein_conformation.protein.parent.entry_name 
                                        for res in excludees if res.protein_conformation.protein.parent!=None]))
            matches = Residue.objects.filter(generic_number__label=parse.gn_indecer(gn,'x',-1))
        elif constriction_in_reference==False:
            matches = Residue.objects.filter(generic_number__label=gn)
        for structure, value in similarity_table.items():  
            protein_object = Protein.objects.get(id=structure.protein_conformation.protein.parent.id)
            try:                            
                for match in matches:
                    if constriction_in_reference==True:
                        if (match.protein_conformation.protein.parent==protein_object and 
                            match.protein_conformation.protein.parent.entry_name not in excludee_proteins):
                            self.constriction_templates.append(structure)
                    elif constriction_in_reference==False:
                        if match.protein_conformation.protein.parent==protein_object:
                            self.constriction_templates.append(structure)
            except:
                pass
        
        for temp in self.constriction_templates:
            try:
                if constriction_in_reference==True:
                    alt_bulge = parse.fetch_residues_from_pdb(temp,
                                                              [parse.gn_indecer(gn,'x',-2),
                                                               parse.gn_indecer(gn,'x',-1),
                                                               parse.gn_indecer(gn,'x',+1),
                                                               parse.gn_indecer(gn,'x',+2)])
                elif constriction_in_reference==False:
                    alt_bulge = parse.fetch_residues_from_pdb(temp,
                                                              [parse.gn_indecer(gn,'x',-2),
                                                               parse.gn_indecer(gn,'x',-1),gn,
                                                               parse.gn_indecer(gn,'x',+1),
                                                               parse.gn_indecer(gn,'x',+2)])
                self.template = temp              
                break
            except:
                self.template = None               
        return alt_bulge
        
class GPCRDBParsingPDB(object):
    ''' Class to manipulate cleaned pdb files of GPCRs.
    '''
    def __init__(self):
        self.segment_coding = {1:'TM1',2:'TM2',3:'TM3',4:'TM4',5:'TM5',6:'TM6',7:'TM7'}
    
    def gn_num_extract(self, gn, delimiter):
        ''' Extract TM number and position for formatting.
        
            @param gn: str, Generic number \n
            @param delimiter: str, character between TM and position (usually 'x')
        '''
        try:
            split = gn.split(delimiter)
            return int(split[0]), int(split[1])
        except:
            return '/', '/'
            
    def gn_indecer(self, gn, delimiter, direction):
        ''' Get an upstream or downstream generic number from reference generic number.
        
            @param gn: str, Generic number \n
            @param delimiter: str, character between TM and position (usually 'x') \n 
            @param direction: int, n'th position from gn (+ or -)
        '''
        split = self.gn_num_extract(gn, delimiter)
        if split[0]!='/':
            if len(str(split[1]))==2:
                return str(split[0])+delimiter+str(split[1]+direction)
            elif len(str(split[1]))==3:
                if direction<0:
                    direction += 1
                return str(split[0])+delimiter+str(int(str(split[1])[:2])+direction)
        return '/'

    def fetch_residues_from_pdb(self, structure, generic_numbers, modify_bulges=False):
        ''' Fetches specific lines from pdb file by generic number (if generic number is
            not available then by residue number). Returns nested OrderedDict()
            with generic numbers as keys in the outer dictionary, and atom names as keys
            in the inner dictionary.
            
            @param structure: Structure, Structure object where residues should be fetched from \n
            @param generic_numbers: list, list of generic numbers to be fetched \n
            @param modify_bulges: boolean, set it to true when used for bulge switching. E.g. you want a 5x461
            residue to be considered a 5x46 residue. 
        '''
        output = OrderedDict()
        atoms_list = []
        for gn in generic_numbers:
            try:
                rotamer = Rotamer.objects.get(structure__protein_conformation=structure.protein_conformation, 
                                              residue__generic_number__label=gn, structure__preferred_chain=structure.preferred_chain)
            except:
                rotamer = Rotamer.objects.get(structure__protein_conformation=structure.protein_conformation, 
                                              residue__sequence_number=gn, structure__preferred_chain=structure.preferred_chain)
            io = StringIO(rotamer.pdbdata.pdb)
            rota_struct = PDB.PDBParser().get_structure('structure', io)[0]
            for chain in rota_struct:
                for residue in chain:
                    for atom in residue:
                        atoms_list.append(atom)
                    if modify_bulges==True and len(gn)==5:
                        output[gn.replace('x','.')[:-1]] = atoms_list
                    else:
                        try:
                            output[gn.replace('x','.')] = atoms_list
                        except:
                            output[gn] = atoms_list
                    atoms_list = []
        return output

    def pdb_array_creator(self, structure=None, filename=None):
        ''' Creates an OrderedDict() from the pdb of a Structure object where residue numbers/generic numbers are 
            keys for the residues, and atom names are keys for the Bio.PDB.Residue objects.
            
            @param structure: Structure, Structure object of protein. When using structure, leave filename=None. \n
            @param filename: str, filename of pdb to be parsed. When using filename, leave structure=None).
        '''
        if structure!=None and filename==None:
            io = StringIO(structure.pdb_data.pdb)
        else:
            io = filename
        residue_array = OrderedDict()
        pdb_struct = PDB.PDBParser(PERMISSIVE=True).get_structure('structure', io)[0]

        assign_gn = as_gn.GenericNumbering(structure=pdb_struct)
        pdb_struct = assign_gn.assign_generic_numbers()
        
        pref_chain = structure.preferred_chain
        for residue in pdb_struct[pref_chain]:
            try:
                if -8.1 < residue['CA'].get_bfactor() < 8.1:
                    gn = str(residue['CA'].get_bfactor())
                    if gn[0]=='-':
                        gn = gn[1:]+'1'
                    elif len(gn)==3:
                        gn = gn+'0'
                    residue_array[gn] = residue.get_list()
                else:
                    residue_array[str(residue.get_id()[1])] = residue.get_list()
            except:
                logging.warning("Unable to parse {} in {}".format(residue, structure))
        
        output = OrderedDict()
        for num, label in self.segment_coding.items():
            output[label] = OrderedDict()
        counter=0
        for gn, res in residue_array.items():
            if '.' in gn:
                seg_label = self.segment_coding[int(gn[0])]
                output[seg_label][gn] = res
            else:
                try:
                    found_res = Residue.objects.get(protein_conformation__protein=structure.protein_conformation.protein.parent,
                                            sequence_number=gn)
                    found_gn = str(found_res.generic_number.label).replace('x','.')
                    if -8.1 < float(found_gn) < 8.1:
                        seg_label = self.segment_coding[int(found_gn[0])]
                        output[seg_label][found_gn] = res
                except:
                    pass
            counter+=1
        return output
   
class CreateStatistics(object):
    ''' Statistics dictionary for HomologyModeling.
    '''
    def __init__(self, reference):
        self.reference = reference
        self.info_dict = OrderedDict()
    
    def __repr__(self):
        return "<{} \n {} \n>".format(self.reference, self.info_dict)
        
    def items(self):
        ''' Returns the OrderedDict().items().
        '''
        return self.info_dict.items()
    
    def add_info(self, info_name, info):
        ''' Adds new information to the statistics dictionary.
        
            @param info_name: str, info name as dictionary key
            @param info: object, any object as value
        '''
        self.info_dict[info_name] = info

