import csv
import os

import bpy

from src.utility.Utility import Utility
from src.utility.ProviderUtility import get_all_mesh_objects
from src.utility.MeshObjectUtility import MeshObject

class SuncgLightingUtility:

    @staticmethod
    def _make_lamp_emissive(obj: MeshObject, light: list, collection_of_mats: dict, lightbulb_emission_strength=15, lampshade_emission_strength=7):
        """ Adds an emission shader to the object materials which are specified in the light list

        :param obj: The blender object.
        :param light: A list of two lists. The first list specifies all materials which should act as a lightbulb, the second one lists all materials corresponding to lampshades.
        :param collection_of_mats: A dictionary that contains materials for lamps, windows and ceilings.
        :param lightbulb_emission_strength: The emission strength that should be used for light bulbs. Default: 15
        :param lampshade_emission_strength: The emission strength that should be used for lamp shades. Default: 7
        """
        for i, m in enumerate(obj.get_materials()):
            mat_name = m.get_name()
            if "." in mat_name:
                mat_name = mat_name[:mat_name.find(".")]
            if mat_name in light[0] or mat_name in light[1]:
                old_mat_name = m.get_name()
                if old_mat_name in collection_of_mats["lamp"]:
                    # this material was used as a ceiling before use that one
                    obj.set_material(i, collection_of_mats["lamp"][old_mat_name])
                    continue
                # copy the material if more than one users is using it
                if m.get_users() > 1:
                    m = m.duplicate()
                    obj.set_material(i, m)
                # rename the material
                m.set_name(m.get_name() + "_emission")

                emission = m.get_nodes_with_type("Emission")
                if not emission:
                    if mat_name in light[0]:
                        # If the material corresponds to light bulb
                        emission_strength = lightbulb_emission_strength
                    else:
                        # If the material corresponds to a lampshade
                        emission_strength = lampshade_emission_strength

                    m.make_emissive(emission_strength, keep_using_base_color=False, emission_color=m.blender_obj.diffuse_color)
                    collection_of_mats["lamp"][old_mat_name] = m

    @staticmethod
    def _make_window_emissive(obj: MeshObject, collection_of_mats: dict):
        """ Makes the given window object emissive.

        For each material with alpha < 1.
        Uses a light path node to make it emit light, but at the same time look like a principle material.
        Otherwise windows would be completely white.

        :param obj: A window object.
        :param collection_of_mats: A dictionary that contains materials for lamps, windows and ceilings.
        """
        for i, m in enumerate(obj.get_materials()):

            # All parameters imported from the .mtl file are stored inside the principled bsdf node
            principled_node = m.get_the_one_node_with_type("BsdfPrincipled")
            alpha = principled_node.inputs['Alpha'].default_value

            if alpha < 1:
                mat_name = m.get_name()
                if mat_name in collection_of_mats["window"]:
                    # this material was used as a ceiling before use that one
                    obj.set_material(i, collection_of_mats["window"][mat_name])
                    continue
                # copy the material if more than one users is using it
                if m.get_users() > 1:
                    m = m.duplicate()
                    obj.set_material(i, m)
                # rename the material
                m.set_name(m.get_name() + "_emission")
                if not m.get_nodes_with_type('Emission'):
                    transparent_node = m.new_node('ShaderNodeBsdfDiffuse')
                    transparent_node.inputs['Color'].default_value[:3] = (0.285, 0.5, 0.48)

                    m.make_emissive(emission_strength=10, keep_using_base_color=False, emission_color=(1, 1, 1, 1), non_emissive_color_socket=transparent_node.outputs['BSDF'])

                collection_of_mats["window"][mat_name] = m

    @staticmethod
    def _make_ceiling_emissive(obj: MeshObject, collection_of_mats: dict, ceiling_emission_strength=1.5):
        """ Makes the given ceiling object emissive, s.t. there is always a little bit ambient light.

        :param obj: The ceiling object.
        :param collection_of_mats: A dictionary that contains materials for lamps, windows and ceilings.
        :param ceiling_emission_strength: The emission strength that should be used for the ceiling. Default: 1.5
        """
        for i, m in enumerate(obj.get_materials()):
            mat_name = m.get_name()
            if mat_name in collection_of_mats["ceiling"]:
                # this material was used as a ceiling before use that one
                obj.set_material(i, collection_of_mats["ceiling"][mat_name])
                continue
            # copy the material if more than one users is using it
            if m.get_users() > 1:
                m = m.duplicate()
                obj.set_material(i, m)
            # rename the material
            m.set_name(m.get_name() + "_emission")

            if not m.get_nodes_with_type("Emission") and m.get_nodes_with_type("BsdfPrincipled"):
                m.make_emissive(emission_strength=ceiling_emission_strength, emission_color=(1, 1, 1, 1), keep_using_base_color=False)
                collection_of_mats["ceiling"][mat_name] = m
    
    @staticmethod
    def light(lightbulb_emission_strength=15, lampshade_emission_strength=7, ceiling_emission_strength=1.5):

        # Read in lights
        lights = {}
        # File format: <obj id> <number of lightbulb materials> <lightbulb material names> <number of lampshade materials> <lampshade material names>
        with open(Utility.resolve_path(os.path.join('resources', "suncg", "light_geometry_compact.txt"))) as f:
            lines = f.readlines()
            for row in lines:
                row = row.strip().split()
                lights[row[0]] = [[], []]

                index = 1

                # Read in lightbulb materials
                number = int(row[index])
                index += 1
                for i in range(number):
                    lights[row[0]][0].append(row[index])
                    index += 1

                # Read in lampshade materials
                number = int(row[index])
                index += 1
                for i in range(number):
                    lights[row[0]][1].append(row[index])
                    index += 1

        # Read in windows
        windows = []
        with open(Utility.resolve_path(os.path.join('resources','suncg','ModelCategoryMapping.csv')), 'r') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                if row["coarse_grained_class"] == "window":
                    windows.append(row["model_id"])
        collection_of_mats = {"lamp": {}, "window": {}, "ceiling": {}}
        
        # Make some objects emit lights
        for obj in get_all_mesh_objects():
            if obj.has_cp("modelId"):
                obj_id = obj.get_cp("modelId")

                # In the case of the lamp
                if obj_id in lights:
                    SuncgLightingUtility._make_lamp_emissive(obj, lights[obj_id], collection_of_mats, lightbulb_emission_strength=15, lampshade_emission_strength=7)

                # Make the windows emit light
                if obj_id in windows:
                    SuncgLightingUtility._make_window_emissive(obj, collection_of_mats)

                # Also make ceilings slightly emit light
                if obj.get_name().startswith("Ceiling#"):
                    SuncgLightingUtility._make_ceiling_emissive(obj, collection_of_mats, ceiling_emission_strength=1.5)