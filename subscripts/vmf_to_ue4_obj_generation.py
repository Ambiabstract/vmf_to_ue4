import re
import os
import sys
import shutil
from collections import defaultdict
import numpy as np
from numpy.linalg import lstsq
from typing import Optional

default_wall_height=128 # in hammer units
obj_description = "#\n# Atmus OBJ\n#\n"
materials_to_remove = ["TOOLSNODRAW", "TOOLSPLAYERCLIP", "TOOLSTRIGGER", "TOOLSSKIP", "TOOLSINVISIBLE", "TOOLSAREAPORTAL"]
#materials_to_remove_cls = ["TOOLSNODRAW", "TOOLSTRIGGER", "TOOLSSKIP"]

# Log file
log_file = open(f"{os.path.splitext(os.path.basename(sys.argv[0]))[0]}_log.txt", 'w', encoding='utf-8')

# Func to log and print something
def log_and_print(data):
    print(data)
    log_file.write(data + '\n')

def prepend_description_to_obj_file(obj_path, obj_description):
    # Читаем содержимое оригинального файла
    with open(obj_path, 'r') as file:
        content = file.read()

    # Добавляем описание в начало
    new_content = obj_description + '\n' + content

    # Перезаписываем файл с новым содержимым
    with open(obj_path, 'w') as file:
        file.write(new_content)

# Function for counting braces
def find_brace_indices(content, start_index):
    open_brace_count = 0
    close_brace_count = 0
    open_brace_index = -1
    close_brace_index = -1

    for i in range(start_index, len(content)):
        if content[i] == '{':
            if open_brace_index == -1:
                open_brace_index = i
            open_brace_count += 1
        elif content[i] == '}':
            close_brace_count += 1
            if open_brace_count == close_brace_count:
                close_brace_index = i
                break

    return open_brace_index, close_brace_index

# Function for extracting content within braces
def extract_block_content(content, start_index):
    open_brace_index, close_brace_index = find_brace_indices(content, start_index)
    if open_brace_index == -1 or close_brace_index == -1:
        return None
    return content[open_brace_index + 1:close_brace_index].strip()

# Function for checking the amount of blocks and their IDs
def check_blocks_info(blocks, name, parent_name):
    blocks_counter=0
    for item in blocks:
        blocks_counter+=1
    log_and_print(f'{blocks_counter} {name} blocks in {parent_name}:')
    
    block_id = re.compile(r'"id"\s+"([^"]+)"', re.DOTALL)
    for item in blocks:
        #log_and_print(item)        # full content output of solid blocks
        #log_and_print("-" * 50)    # divider for convenience
        
        block_id_match = block_id.match(item)
        if block_id_match:
            log_and_print(block_id_match.group(0))
            
    log_and_print("")
    
# Function for extracting solid blocks from VMF
def extract_solids_from_vmf(vmf_content):
    solid_start_indices = [m.start() for m in re.finditer(r'solid\s*{\s*"id"\s*"', vmf_content)]
    solid_blocks = [extract_block_content(vmf_content, start) for start in solid_start_indices]
    
    check_blocks_info(solid_blocks, "solid", "VMF")
    #log_and_print("")
    
    return solid_blocks

# Extract 'side' blocks from a 'solid' block
def extract_sides_from_solid(solid_content):
    side_start_indices = [m.start() for m in re.finditer(r'side\s*{\s*"id"\s*"', solid_content)]
    side_blocks = [extract_block_content(solid_content, start) for start in side_start_indices]
    
    solid_parent_id_pattern = re.compile(r'"id"\s+"([^"]+)"', re.DOTALL)
    solid_match = solid_parent_id_pattern.match(solid_content)
    if solid_match:
        solid_parent_id = solid_match.group(1)
        #log_and_print(f'solid_content id: {solid_parent_id}')

    check_blocks_info(side_blocks, "side", f"solid {solid_parent_id}")
    
    return side_blocks

# Function to extract vertices from a 'side' block content
def extract_vertices_from_side(side_content):
    # Regular expression pattern for extracting vertices
    vertices_re = re.compile(r'"v" "(.*?)"', re.DOTALL)
    
    # Extract vertices
    vertices_matches = vertices_re.findall(side_content)
    vertices = [tuple(map(float, v.split())) for v in vertices_matches]
    vertices.reverse()  # reverse the vertex order to have correct normals in the final mesh
    
    #log_and_print(f"Vertices:\n{vertices}\n")
    
    return vertices

# Function to extract key attributes from a 'side' block content
def extract_side_attributes(side_content):
    # Regular expression patterns for extracting attributes
    plane_re = re.compile(r'"plane"\s+"([^"]+)"', re.DOTALL)
    material_re = re.compile(r'"material"\s+".*/([^/"]+)"', re.DOTALL)
    uaxis_re = re.compile(r'"uaxis"\s+"([^"]+)"', re.DOTALL)
    vaxis_re = re.compile(r'"vaxis"\s+"([^"]+)"', re.DOTALL)
    
    # Extract attributes
    plane_match = plane_re.search(side_content)
    material_match = material_re.search(side_content)
    uaxis_match = uaxis_re.search(side_content)
    vaxis_match = vaxis_re.search(side_content)
    
    plane = plane_match.group(1) if plane_match else None
    material = material_match.group(1) if material_match else None
    uaxis = uaxis_match.group(1) if uaxis_match else None
    vaxis = vaxis_match.group(1) if vaxis_match else None
    
    #log_and_print(f"Material:\n{material}\n")
    #log_and_print(f"UVs:\n{uaxis}\n{vaxis}\n")
    
    return plane, material, uaxis, vaxis
    
# Function to extract smoothing group from a 'side' block content
def extract_smoothing_group(side_content):
    sg_re = re.compile(r'"smoothing_groups"\s+"([^"]+)"', re.DOTALL)
    
    sg_match = sg_re.search(side_content)
    
    sg = sg_match.group(1) if sg_match else None
    
    #log_and_print(f"smoothing_group:\n{sg}\n")
    
    return sg

def get_vtf_path(side_content, vmf_path):
    mat_path_re = re.compile(r'"material"\s+"([^"]+)"', re.DOTALL)

    mat_path_match = mat_path_re.search(side_content)
    
    mat_path_raw = mat_path_match.group(1) if mat_path_match else None
   
    gameinfo_path = None
    vtf_path = None
    
    gameinfo_found = False
    for dirpath, dirnames, filenames in os.walk(os.path.dirname(os.path.dirname(vmf_path))):
        if "gameinfo.txt" in filenames:
            gameinfo_path = dirpath
            gameinfo_found = True
            break
    
    if not gameinfo_found:
        for dirpath, dirnames, filenames in os.walk(os.path.dirname(os.path.dirname(os.path.dirname(vmf_path)))):
            if "gameinfo.txt" in filenames:
                gameinfo_path = dirpath
                gameinfo_found = True
                break
    
    if not gameinfo_found:
        log_and_print("Cant find gameinfo!!!")
            
    materials_path = gameinfo_path + "/materials"
    custom_path = gameinfo_path + "/custom"

    mat_file_name = ((mat_path_raw.split("/")[-1]) + ".vmt").lower()
    material_name = mat_path_raw.split("/")[-1]
    vmt_path = "None"
    for root, dirs, files in os.walk(materials_path):
        for file in files:
            if file.lower() == mat_file_name:
                vmt_path = os.path.join(root, mat_file_name)
                break
        #log_and_print(f"root: {root}\n")
        #log_and_print(f"dirs: {dirs}\n")
        #log_and_print(f"files: {files}\n")
    if vmt_path == "None":
        for root, dirs, files in os.walk(custom_path):
            for file in files:
                #log_and_print(f"{file.lower()}\t{mat_file_name}\n")   
                if file.lower() == mat_file_name:
                    vmt_path = os.path.join(root, mat_file_name)
                    break
            #log_and_print(f"root: {root}\n")
            #log_and_print(f"dirs: {dirs}\n")
            #log_and_print(f"files: {files}\n")
    
    #log_and_print(f"vmt_path: {vmt_path}\n")
    
    if os.path.exists(vmt_path):
        with open(vmt_path, 'r') as file:
            vmt_content = file.read()
        
        vtf_pattern = r'\$basetexture\s+"[^"]+/([^"/]+)"'
        vtf_match = re.search(vtf_pattern, vmt_content, re.IGNORECASE)
        if vtf_match:
            vtf_name = vtf_match.group(1)
        
        vtf_raw_path_pattern = r'\$basetexture\s+"([^"]+)"'
        vtf_raw_path_match = re.search(vtf_raw_path_pattern, vmt_content, re.IGNORECASE)
        if vtf_raw_path_match:
            vtf_raw_path = vtf_raw_path_match.group(1)
        
            vtf_path = materials_path + "/" + vtf_raw_path + ".vtf"
        
        if vtf_path is not None:
            if not os.path.isfile(vtf_path):
                tex_file_name = ((vtf_raw_path.split("/")[-1]) + ".vtf").lower()
                for root, dirs, files in os.walk(custom_path):
                    for file in files:
                        #log_and_print(f"{file.lower()}\t{tex_file_name}\n")   
                        if file.lower() == tex_file_name:
                            vtf_path = os.path.join(root, tex_file_name)
                            break
        else:
            log_and_print(f"{material_name} vtf not found!")
            
        #log_and_print(f"vtf_path: {vtf_path}\n")
        return vtf_path
    else:
        log_and_print(f"{material_name} vmt not found!")
        return None

def get_vtf_resolution(file_path):
    if file_path is None:
        #log_and_print(f"VTF file path is None! Cant get resolution!")
        return None

    try:
        file_path = file_path.replace('/', '\\')
        with open(file_path, 'rb') as f:
            vtf_buffer = f.read()
    except Exception as e:
        return f"An error occurred: {e}"

    # Extracting the width and height from the buffer
    # According to the VTF header structure, width and height are at 16-byte and 18-byte offsets (unsigned short)
    width = int.from_bytes(vtf_buffer[16:18], 'little')
    height = int.from_bytes(vtf_buffer[18:20], 'little')
    
    #log_and_print(f"vtf width: {width}\n")
    #log_and_print(f"vtf height: {height}\n")
    return (width, height)

def find_plane_normal_from_list(vertices):
    """
    Finds the exact normal vector of the plane defined by the given vertices.
    
    Parameters:
        vertices (list): A list of tuples containing at least 3 points in 3D space that define a plane.
        
    Returns:
        normal (ndarray): A 1 x 3 numpy array containing the components of the normal vector.
    """
    # Convert the list of tuples to a numpy array
    points = np.array(vertices)
    
    # Take the first three vertices to define two vectors on the plane
    A, B, C = points[0], points[1], points[2]
    
    # Calculate the vectors AB and AC
    AB = B - A
    AC = C - A
    
    # Calculate the cross product of AB and AC to get the normal vector
    normal = np.cross(AB, AC)
    
    # Normalize the normal vector
    normal = normal / np.linalg.norm(normal)
    
    return normal

def convert_vmf_to_obj(vmf_content, vmf_path, default_units_scale, default_texture_scale):
    unit_scale = 1.00*float(default_units_scale)/1
    vmf_name = vmf_path.split('\\')[-1].split('.')[0]
    
    #log_and_print(f"Start convert_vmf_to_obj...\n")
    log_and_print(f"\nStart converting {vmf_name}...")
    
    obj_data = ""
    #obj_data = "".join(f'#\n# {obj_description}\n#\n\n')
    solid_contents = extract_solids_from_vmf(vmf_content)
    solid_content_index=0
    vertex_index = 0
    
    obj_data += f'o {vmf_name}\n\n'
    
    for solid_content in solid_contents:
        log_and_print("-" * 50)
        solid_content_index+=1
        solid_id_pattern = re.compile(r'"id"\s+"([^"]+)"', re.DOTALL)
        solid_match = solid_id_pattern.match(solid_content)
        if solid_match:
            solid_id = solid_match.group(1)
        
        #if int(solid_id) <= 9:
        #    tripled_solid_id = "00" + f'{solid_id}'
        #elif int(solid_id) <= 99:
        #    tripled_solid_id = "0" + f'{solid_id}'
        #else:
        #    tripled_solid_id = solid_id
        tripled_solid_id = solid_id # fuck zeros because vmf does not have it - SSH, 02 05 2024
        
        log_and_print(f"Converting Solid_{tripled_solid_id}...")
        
        converted_solid = ""
        converted_solid += f'#\n# Solid_{tripled_solid_id}\n#\n\n'
        
        #converted_solid += f'o Solid_{tripled_solid_id}\n'
        converted_solid += f'g Solid_{tripled_solid_id}\n'
        
        sides = extract_sides_from_solid(solid_content)
        side_index = 0
        for side in sides:
            side_index += 1
          
            side_id_pattern = re.compile(r'"id"\s+"([^"]+)"', re.DOTALL)
            side_match = side_id_pattern.match(side)
            if side_match:
                side_id = side_match.group(1)
                
            #if int(side_id) <= 9:
            #    tripled_side_id = "00" + f'{side_id}'
            #elif int(side_id) <= 99:
            #    tripled_side_id = "0" + f'{side_id}'
            #else:
            #    tripled_side_id = side_id
            tripled_side_id = side_id # fuck zeros because vmf does not have it - SSH, 02 05 2024
            
            vertices = extract_vertices_from_side(side)
            plane, material, uaxis, vaxis = extract_side_attributes(side)
            
            vtf_path = get_vtf_path(side, vmf_path)
            
            vtf_resolution = get_vtf_resolution(vtf_path)
            #log_and_print(f'vtf_resolution: {vtf_resolution}')
            if vtf_resolution is not None:
                vtf_width, vtf_height = get_vtf_resolution(vtf_path)
                u_tex = vtf_width
                v_tex = vtf_height
            else: 
                #log_and_print(f'vtf not found!!!')
                vtf_width, vtf_height = None, None
                u_tex = default_wall_height/(float(default_texture_scale)) #512=128/0.25
                v_tex = default_wall_height/(float(default_texture_scale)) #512=128/0.25
            
            #log_and_print(f'u_tex: {u_tex}')
            #log_and_print(f'v_tex: {u_tex}')
            
            #log_and_print(f'vtf_width: {vtf_width}')
            #log_and_print(f'vtf_height: {vtf_height}')
    
            for vert_x, vert_y, vert_z in vertices:
                vertex_index += 1
                converted_solid += f'v {vert_x * unit_scale} {vert_z * unit_scale} {-vert_y * unit_scale}\n'
                
                # UV
                uv_pattern = re.compile(r"(-?\d+\.?\d*)", re.DOTALL)
                u_match = re.findall(uv_pattern, uaxis)
                if u_match:
                    ux, uy, uz, u_shift, u_tex_scale = map(float, u_match)
                v_match = re.findall(uv_pattern, vaxis)
                if v_match:
                    vx, vy, vz, v_shift, v_tex_scale = map(float, v_match)

                #u = ((vert_x * ux + vert_y * uy + vert_z * uz) / texel_dencity_units + u_shift / texel_dencity_tex) * texel_dencity_tex / u_tex
                #v = -((vert_x * vx + vert_y * vy + vert_z * vz) / texel_dencity_units + v_shift / texel_dencity_tex) * texel_dencity_tex / v_tex
                
                #u = ((vert_x * ux + vert_y * uy + vert_z * uz) + u_shift * float(default_texture_scale)) / (float(default_texture_scale) * u_tex)
                #v = -((vert_x * vx + vert_y * vy + vert_z * vz) + v_shift * float(default_texture_scale)) / (float(default_texture_scale) * v_tex)
                
                u = ((vert_x * ux + vert_y * uy + vert_z * uz) + u_shift * u_tex_scale) / (u_tex_scale * u_tex)
                v = -((vert_x * vx + vert_y * vy + vert_z * vz) + v_shift * v_tex_scale) / (v_tex_scale * v_tex)
                
                
                converted_solid += f'vt {u} {v}\n'
                
                nx, ny, nz = find_plane_normal_from_list(vertices)
                converted_solid += f'vn {nx} {nz} {-ny} \n'
            
            converted_solid += f'usemtl {material}\n'           # materials per side
            
            sg = extract_smoothing_group(side)
            
            converted_solid += f's {sg}\n'
            
            #converted_solid += f's off\n'                       # temp smoothing groups
            #converted_solid += f's 1\n'                        # temp smoothing groups   
            
            #converted_solid += f'o Side_{tripled_side_id}\n'    # temp object
            #converted_solid += f'g Side_{tripled_side_id}\n'    # temp group

            # Faces generation
            converted_solid += f'f '
            for i in range(len(vertices)):
                converted_solid += f'{vertex_index-len(vertices)+i+1}/{vertex_index-len(vertices)+i+1}/{vertex_index-len(vertices)+i+1} '
            converted_solid += f'\n'
            
        converted_data = converted_solid
        
        if converted_data is not None:
            obj_data += converted_data
            obj_data += "\n"
        else:
            print(f"Warning: convert_solid_to_obj_with_uvs returned None for solid_content: {solid_content_index}")
    
    return obj_data

# Function for merge objects by material and remove geometry with some material (TOOLSNODRAW)
def merge_and_filter_objects_by_material_inplace(obj_file_path, materials_to_remove=None):
    temp_file_path = obj_file_path + '.tmp'
    obj_file_name = obj_file_path.split('\\')[-1].split('.')[0]
    
    material_to_faces_and_smoothing_groups = defaultdict(list)
    current_material = None
    current_smoothing_group = None
    
    vertices = []
    texture_coords = []
    normals = []
    
    if materials_to_remove is None:
        materials_to_remove = set()
    
    # Read the OBJ file and group faces by material, also collect vertices, texture coordinates, and normals
    with open(obj_file_path, 'r') as infile:
        for line in infile:
            line = line.strip()
            if line.startswith('usemtl'):
                current_material = line.split()[1]
            elif line.startswith('s '):
                current_smoothing_group = line
            elif line.startswith('f'):
                if current_material is not None and current_material not in materials_to_remove:
                    material_to_faces_and_smoothing_groups[current_material].append((current_smoothing_group, line))
            elif line.startswith('v '):
                vertices.append(line)
            elif line.startswith('vt '):
                texture_coords.append(line)
            elif line.startswith('vn '):
                normals.append(line)
    
    # Write the new content to a temporary OBJ file
    with open(temp_file_path, 'w') as outfile:
        #outfile.write(f'#\n# {obj_description}\n#\n\n')
        #outfile.write(f'o {obj_file_name}_visible_geometry\n\n')
        
        # Write vertices, texture coordinates, and normals
        outfile.write('\n'.join(vertices) + '\n')
        outfile.write('\n'.join(texture_coords) + '\n')
        outfile.write('\n'.join(normals) + '\n')
        
        # Write grouped faces by material
        for material, faces_and_smoothing_groups in material_to_faces_and_smoothing_groups.items():
            outfile.write(f'g {material}\n')
            outfile.write(f'usemtl {material}\n')
            last_smoothing_group = None
            for smoothing_group, face in faces_and_smoothing_groups:
                if smoothing_group != last_smoothing_group:
                    outfile.write(smoothing_group + '\n')
                    last_smoothing_group = smoothing_group
                outfile.write(face + '\n')
                
    # Replace the original OBJ file with the new content
    shutil.move(temp_file_path, obj_file_path)

def optimize_vertexes(obj_file_path: str, remove_vn: Optional[bool] = False):
    unique_vertices = {}
    blocks = []
    other_lines = []
    index_offset = 1
    new_index = 1
    current_block = []
    current_smoothing_group = '0'  # Default smoothing group
    last_group_name = None  # Last group name
    first_smoothing_group_for_last_group = True  # Flag to check if it's the first smoothing group for the last 'g' group

    with open(obj_file_path, 'r') as f:
        lines = [line.strip() for line in f.readlines()]

    for line in lines:
        if line.startswith('v '):
            vertex_str = ' '.join(format(float(x), '.6f') for x in line[2:].split())
            if vertex_str not in unique_vertices:
                unique_vertices[vertex_str] = new_index
                new_index += 1
        elif line.startswith('f '):
            vertex_parts = re.findall(r'(\d+/[\d/]*)', line)
            updated_face = 'f'
            for vp in vertex_parts:
                vertex_idx, *other_indices = vp.split('/')
                old_index = int(vertex_idx) - index_offset
                vertex_str = ' '.join(format(float(x), '.6f') for x in lines[old_index][2:].split())
                new_index = unique_vertices[vertex_str]

                if remove_vn and current_smoothing_group not in ['0', 'off']:
                    updated_face += f' {new_index}/' + '/'.join(other_indices[:-1])
                else:
                    updated_face += f' {new_index}/' + '/'.join(other_indices)
            current_block.append(updated_face)
        elif line.startswith('s '):
            new_smoothing_group = line[2:].strip()
            if new_smoothing_group != current_smoothing_group:
                current_smoothing_group = new_smoothing_group
                if current_block:
                    blocks.append(current_block)
                current_block = [f's {current_smoothing_group}']
                if last_group_name and not first_smoothing_group_for_last_group:
                    #current_block.insert(0, f'g {last_group_name}_sg{current_smoothing_group}')
                    pass
                first_smoothing_group_for_last_group = False  # Reset the flag as we have encountered a smoothing group for this 'g' group
        elif line.startswith('g '):
            last_group_name = line[2:].strip()
            first_smoothing_group_for_last_group = True  # Reset the flag as we have a new 'g' group
            if current_block:
                blocks.append(current_block)
            current_block = [line.strip()]
        elif line.startswith('usemtl '):
            current_block.append(line.strip())
        else:
            other_lines.append(line.strip())

    if current_block:
        blocks.append(current_block)

    with open(obj_file_path, 'w') as f:
        #f.write(f'#\n# {obj_description}\n#\n')
        
        f.write(f'\n# Vertices:\n')
        for vertex_str, index in unique_vertices.items():
            f.write(f'v {vertex_str}\n')
        
        f.write(f'\n# UV and vertex normals:\n')
        for line in other_lines:
            f.write(f'{line}\n')
        
        f.write(f'\n# Groups of faces by materials and smoothgroups:\n')
        for block in blocks:
            for line in block:
                f.write(f'{line}\n')

def find_smoothed_faces(file_path):
    smoothed_faces = {}
    current_s = '0'  # Initialize with a value that excludes non-smoothed faces
    global_face_count = 0

    with open(file_path, 'r') as f:
        for line in f:
            line = line.strip()
            tokens = line.split()
            if len(tokens) == 0:
                continue

            # Processing 's' string
            if tokens[0] == 's':
                current_s = tokens[1]
            
            # Processing 'f' string
            elif tokens[0] == 'f':
                global_face_count += 1
                #log_and_print(f'\nglobal_face_count:{global_face_count}\n')
                #log_and_print(f'\ncurrent_s:{current_s}\n')
                
                if current_s not in {'0', 'off'}:
                    face_key = f'f_{global_face_count}'
                    face_vertices = []
                    for face_data in tokens[1:]:
                        v_index, vt_index, vn_index = map(int, face_data.split('/'))
                        face_vertex = [v_index, vt_index, vn_index]
                        face_vertices.append(face_vertex)
                    smoothed_faces[face_key] = face_vertices

    return smoothed_faces

# Does not work and useless
#def find_identical_vertices(obj_file_path, target_vertex_index):
#    identical_vertex_indices = []
#    target_vertex_value = None
#
#    with open(obj_file_path, 'r') as f:
#        lines = f.readlines()
#
#    vertex_count = 0
#    for i, line in enumerate(lines):
#        line = line.strip()
#        if line.startswith("v "):  # This line defines a vertex
#            vertex_count += 1
#            tokens = line.split()
#            vertex_value = tuple(map(float, tokens[1:]))  # Extract x, y, z coordinates and convert them to float
#
#            if vertex_count == target_vertex_index:  # This is the target vertex
#                target_vertex_value = vertex_value
#
#            if target_vertex_value and vertex_value == target_vertex_value:
#                identical_vertex_indices.append(vertex_count)
#
#    return identical_vertex_indices

def find_smoothed_vertices(file_path):
    smoothed_vertices = {}
    current_s = '0'  # Initialize with a value that excludes non-smoothed faces
    global_vertices_count = 0

    smoothed_faces = find_smoothed_faces(file_path)
    
    for face in smoothed_faces:
        for face_vertex in smoothed_faces[face]:
            for face_vertex in smoothed_faces[face]:
                v_index, vt_index, vn_index = face_vertex
                smoothed_vertices[v_index] = face, face_vertex
    #log_and_print(f'smoothed_vertices:\n{smoothed_vertices}')
    
    return smoothed_vertices

# Function to read a specific vertex from an OBJ file by index
def read_vertex_from_obj(obj_file_path, vertex_number):
    vertex_count = 0
    vertex_value = None
    
    # Open the OBJ file and read line by line
    with open(obj_file_path, 'r') as file:
        for line in file:
            # Lines that define vertices start with 'v'
            if line.startswith('v '):
                vertex_count += 1
                
                # If the current vertex is the one we are looking for, store its value
                if vertex_count == vertex_number:
                    vertex_value = line.strip().split(' ')[1:]
                    break
                    
    if vertex_value is None:
        return "Vertex not found."
    
    return ' '.join(vertex_value)

# Smoothing groups to vertex normals
def sg_to_vn(obj_file_path):
    smoothed_faces = find_smoothed_faces(obj_file_path) # Vocab with faces and vertexes
    smoothed_vertices = find_smoothed_vertices(obj_file_path)
    vertex_normals = {}
    
    #log_and_print(f'\nSmoothed faces separated:')
    #for face in smoothed_faces:
    #    log_and_print(f'{face}')
    #    for face_vertex in smoothed_faces[face]:
    #        log_and_print(f'    {face_vertex}')
    #        
    #for face in smoothed_faces:
    #    for face_vertex in smoothed_faces[face]:
    #        v_index, vt_index, vn_index = face_vertex
            
    #log_and_print(f'smoothed_vertices:\n{smoothed_vertices}')
    
    #log_and_print(f'smoothed_faces: {smoothed_faces}')
    for face, vertices in smoothed_faces.items():
        #log_and_print(f'face: {face}')
        #log_and_print(f'vertices: {vertices}')
        for vertex_data in vertices:
            v, vt, vn = vertex_data
            #log_and_print(f'v: {v}')
            #log_and_print(f'vt: {vt}')
            #log_and_print(f'vn: {vn}')
            vertex_key = f'v_{v}'
            
            # Initialize the list for this vertex if it's not already in the dictionary
            if vertex_key not in vertex_normals:
                vertex_normals[vertex_key] = []
            
            vertex_normals[vertex_key].append(vn)
            
    #log_and_print(f'vertex_normals: {vertex_normals}')
    
    #for face in smoothed_faces:
    #    for face_vertex in smoothed_faces[face]:
    #        for face_vertex in smoothed_faces[face]:
    #            v_index, vt_index, vn_index = face_vertex
    
    #log_and_print(f'smoothed_vertices:')
    #for vertex_index in smoothed_vertices:
        #log_and_print(f'{vertex_index}')
        
        #find_identical_vertices(obj_file_path, vertex_index):
        #log_and_print(f'Same vertices:')
        #log_and_print(f'    {ident_v}')
    
    #for vertex_index in smoothed_vertices:
    #    for content in smoothed_vertices[vertex_index]:
    #        log_and_print(f'vertex content: {content}')
    #        #face, face_vertex = content
    #        #log_and_print(f'vertex: {face_vertex}')
    #find_identical_vertices(obj_file_path, target_vertex_index)
    
    
        #for vertex in smoothed_vertices:
    #    log_and_print(f'vertex {vertex}:')
    #    vertex_content = smoothed_vertices[vertex]:
    #        log_and_print(f'    {vertex_content}:')
    
    #with open(file_path, 'r') as f:
    #    for line in f:
    #        line = line.strip()
    #        tokens = line.split()
    #        if len(tokens) == 0:
    #            continue
    #
    #        # Processing 's' string
    #        if tokens[0] == 's':
    #            current_s = tokens[1]
    #        
    #        # Processing 'f' string
    #        elif tokens[0] == 'f':
    #            global_face_count += 1
    #            #log_and_print(f'\nglobal_face_count:{global_face_count}\n')
    #            #log_and_print(f'\ncurrent_s:{current_s}\n')
    #            
    #            if current_s not in {'0', 'off'}:
    #                face_key = f'f_{global_face_count}'
    #                face_vertices = []
    #                for face_data in tokens[1:]:
    #                    v_index, vt_index, vn_index = map(int, face_data.split('/'))
    #                    face_vertex = [v_index, vt_index, vn_index]
    #                    face_vertices.append(face_vertex)
    #                smoothed_faces[face_key] = face_vertices
    #
    #return smoothed_faces
    
    
    
    
    
    
    
    
    
    #smoothed_faces = {
    #'f': [face_vertex, face_vertex, face_vertex],
    #}
    #
    #face_vertex = [v_index, vt_index, vn_index]
    #
    #face_pattern = re.compile(r'f\s+((\d+/\d+/\d+\s+)+\d+/\d+/\d+)', re.DOTALL)
    #
    #u_match = re.findall(uv_pattern, uaxis)
    #            if u_match:
    #                ux, uy, uz, u_shift, u_tex_scale = map(float, u_match)
    

    
    #with open(obj_file_path, 'r') as f:
    #    lines = [line.strip() for line in f.readlines()]
    #    
    #for line in lines:
    #    if line.startswith('f ')
    #        
    #
    #for line in lines:
    #    if line.startswith('v '):
    #        vertex_str = ' '.join(format(float(x), '.6f') for x in line[2:].split())
    #        if vertex_str not in unique_vertices:
    #            unique_vertices[vertex_str] = new_index
    #            new_index += 1
    #    elif line.startswith('f '):
    #        vertex_parts = re.findall(r'(\d+/[\d/]*)', line)
    #        updated_face = 'f'
    #        for vp in vertex_parts:
    #            vertex_idx, *other_indices = vp.split('/')
    #            old_index = int(vertex_idx) - index_offset
    #            vertex_str = ' '.join(format(float(x), '.6f') for x in lines[old_index][2:].split())
    #            new_index = unique_vertices[vertex_str]
    #
    #            if remove_vn and current_smoothing_group not in ['0', 'off']:
    #                updated_face += f' {new_index}/' + '/'.join(other_indices[:-1])
    #            else:
    #                updated_face += f' {new_index}/' + '/'.join(other_indices)
    #        current_block.append(updated_face)
    #    elif line.startswith('s '):
    #        new_smoothing_group = line[2:].strip()
    #        if new_smoothing_group != current_smoothing_group:
    #            current_smoothing_group = new_smoothing_group
    #            if current_block:
    #                blocks.append(current_block)
    #            current_block = [f's {current_smoothing_group}']
    #            if last_group_name and not first_smoothing_group_for_last_group:
    #                current_block.insert(0, f'g {last_group_name}_sg{current_smoothing_group}')
    #            first_smoothing_group_for_last_group = False  # Reset the flag as we have encountered a smoothing group for this 'g' group
    #    elif line.startswith('g '):
    #        last_group_name = line[2:].strip()
    #        first_smoothing_group_for_last_group = True  # Reset the flag as we have a new 'g' group
    #        if current_block:
    #            blocks.append(current_block)
    #        current_block = [line.strip()]
    #    elif line.startswith('usemtl '):
    #        current_block.append(line.strip())
    #    else:
    #        other_lines.append(line.strip())
    #
    #if current_block:
    #    blocks.append(current_block)
    #
    #with open(obj_file_path, 'w') as f:
    #    for vertex_str, index in unique_vertices.items():
    #        f.write(f'v {vertex_str}\n')
    #    for line in other_lines:
    #        f.write(f'{line}\n')
    #    for block in blocks:
    #        for line in block:
    #            f.write(f'{line}\n')

def ucx_generation(vmf_content, vmf_path, default_units_scale):
    unit_scale = 1.00*float(default_units_scale)/1
    vmf_name = vmf_path.split('\\')[-1].split('.')[0]
    
    #log_and_print(f"Start convert_vmf_to_obj...\n")
    log_and_print(f"\nStart generating UCX collision for {vmf_name}...")
    
    obj_data = ""
    #obj_data = "".join(f'#\n# {obj_description}\n#\n\n')
    solid_contents = extract_solids_from_vmf(vmf_content)
    solid_content_index=0
    vertex_index = 0
    
    obj_data += f'\n# UCX COLLISION GROUPS:\n'
    #obj_data += f'\no UCX_{vmf_name}\n'
    
    # Fake visible mesh for playerclip CLS reading by UE4
    obj_data += f'\n# Fake visible mesh for playerclip CLS reading by UE4:\n'
    obj_data += f'g TOOLSPLAYERCLIP_dummy\n'
    obj_data += f'v 0 -256 0\n'
    obj_data += f'v 0.001 -256 0\n'
    obj_data += f'v 0 -256 0.001\n'
    obj_data += f'usemtl TOOLSPLAYERCLIP\n'
    obj_data += f'f 1 2 3\n'
    vertex_index += 3
    
    for solid_content in solid_contents:
        log_and_print("-" * 50)
        solid_content_index+=1
        solid_id_pattern = re.compile(r'"id"\s+"([^"]+)"', re.DOTALL)
        solid_match = solid_id_pattern.match(solid_content)
        if solid_match:
            solid_id = solid_match.group(1)
        
        #if int(solid_id) <= 9:
        #    tripled_solid_id = "00" + f'{solid_id}'
        #elif int(solid_id) <= 99:
        #    tripled_solid_id = "0" + f'{solid_id}'
        #else:
        #    tripled_solid_id = solid_id
        tripled_solid_id = solid_id # fuck zeros because vmf does not have it - SSH, 02 05 2024
        
        log_and_print(f"Converting UCX_Solid_{tripled_solid_id}...")
        
        converted_solid = ""
        converted_solid += f'#\n# UCX_Solid_{tripled_solid_id}\n#\n\n'
        
        #converted_solid += f'o UCX_Solid_{tripled_solid_id}\n'
        converted_solid += f'g UCX_Solid_{tripled_solid_id}\n'
        #converted_solid += f'g UCX_{material}_{tripled_solid_id}\n'
        
        sides = extract_sides_from_solid(solid_content)
        side_index = 0
        for side in sides:
            side_index += 1
          
            side_id_pattern = re.compile(r'"id"\s+"([^"]+)"', re.DOTALL)
            side_match = side_id_pattern.match(side)
            if side_match:
                side_id = side_match.group(1)
                
            #if int(side_id) <= 9:
            #    tripled_side_id = "00" + f'{side_id}'
            #elif int(side_id) <= 99:
            #    tripled_side_id = "0" + f'{side_id}'
            #else:
            #    tripled_side_id = side_id
            tripled_side_id = side_id # fuck zeros because vmf does not have it - SSH, 02 05 2024
            
            vertices = extract_vertices_from_side(side)
            plane, material, uaxis, vaxis = extract_side_attributes(side)
            #plane, material = extract_side_attributes(side)
    
            #converted_solid += f'g UCX_{material}_{tripled_solid_id}_{tripled_side_id}\n'
            
            for vert_x, vert_y, vert_z in vertices:
                vertex_index += 1
                converted_solid += f'v {vert_x * unit_scale} {vert_z * unit_scale} {-vert_y * unit_scale}\n'
                
                #converted_solid += f'vt {u} {v}\n'
                
                #nx, ny, nz = find_plane_normal_from_list(vertices)
                #converted_solid += f'vn {nx} {nz} {-ny} \n'
            
            converted_solid += f'usemtl UCX_{material}_{tripled_solid_id}\n'           # materials per side
            #converted_solid += f'usemtl UCX_COLLISION\n'           # materials per side
            
            #sg = extract_smoothing_group(side)
            
            converted_solid += f's 1\n'

            # Faces generation
            converted_solid += f'f '
            for i in range(len(vertices)):
                converted_solid += f'{vertex_index-len(vertices)+i+1} '
            converted_solid += f'\n'
            
        converted_data = converted_solid
        
        if converted_data is not None:
            obj_data += converted_data
            obj_data += "\n"
        else:
            print(f"Warning: convert_solid_to_obj_with_uvs returned None for solid_content: {solid_content_index}")
    
    return obj_data

def append_cls_data(obj_path, obj_data):
    # Чтение содержимого из obj файла
    with open(obj_path, 'r') as file:
        original_content = file.readlines()
    
    # Определение последнего индекса вертекса в оригинальном файле
    last_vertex_index = 0
    for line in original_content:
        if line.startswith('v '):  # Ищем строки с вертексами
            last_vertex_index += 1  # Увеличиваем счетчик вертексов
    
    # Изменение индексов вертексов в добавляемых данных
    modified_data = []
    for line in obj_data.split('\n'):
        if line.startswith('f '):  # Ищем строки с фейсами
            numbers = re.findall(r'\d+', line)  # Извлечение индексов из строки фейса
            incremented_numbers = ' '.join(str(int(num) + last_vertex_index) for num in numbers)
            modified_line = f'f {incremented_numbers}\n'
            modified_data.append(modified_line)
        else:
            modified_data.append(line + '\n')
    
    # Добавление измененных данных в оригинальный файл
    with open(obj_path, 'a') as file:
        file.writelines(modified_data)

def generate_ucs_groups(obj_path):
    # Считываем содержимое файла
    with open(obj_path, 'r') as file:
        lines = file.readlines()
    
    # Подготавливаем список для новых строк
    new_lines = []
    is_group = False
    group_lines = []

    new_lines.append('\n# UCX COLLISION GROUPS:\n')
    
    # Ищем группы и копируем их содержимое
    for line in lines:
        if line.startswith('g '):  # Начало новой группы
            if is_group:  # Если уже в группе, добавляем её копию в new_lines
                new_lines.append('g UCX_' + group_name + '\n')
                new_lines.extend(group_lines)
            group_name = line.split()[1]  # Имя группы
            group_lines = []  # Сброс списка строк группы
            is_group = True  # Маркер начала группы
        if is_group and line.startswith('f '):  # Строки с 'f', которые нужно копировать
            group_lines.append(line)
    
    # Добавляем последнюю группу, если файл закончился
    if is_group:
        new_lines.append('g UCX_' + group_name + '\n')
        new_lines.extend(group_lines)
    
    # Добавляем оригинальные строки и новые строки в файл
    with open(obj_path, 'w') as file:
        file.writelines(lines + new_lines)

def main():
    log_and_print(f'OBJ PROCESSING STARTED!')
    
    # Assuming the VMF files are dragged onto the script
    gamedir_path, vmf_file_path, default_units_scale, default_texture_scale = sys.argv[1:]
    
    log_and_print(f'gamedir_path: {gamedir_path}')
    log_and_print(f'vmf_file_path: {vmf_file_path}')
    log_and_print(f'default_units_scale: {default_units_scale}')
    log_and_print(f'default_texture_scale: {default_texture_scale}')
    
    vmf_path = vmf_file_path
    
    #log_and_print(f'vmf_path: {vmf_path}')
    if vmf_path.lower().endswith('.vmf'):
        with open(vmf_path, 'r') as f:
            vmf_content = f.read()
        obj_content = convert_vmf_to_obj(vmf_content, vmf_path, default_units_scale, default_texture_scale)
        
        # Save the OBJ content to a file in the same directory as the VMF file
        obj_file_path = os.path.join(os.path.dirname(vmf_path), f"{os.path.splitext(os.path.basename(vmf_path))[0]}.obj")
        with open(obj_file_path, 'w') as f:
            f.write(obj_content)
        
        #generate_ucs_groups(obj_file_path)
        
        # Merge by materials
        merge_and_filter_objects_by_material_inplace(obj_file_path, materials_to_remove)
        #merge_and_filter_objects_by_material_inplace(obj_file_path, "SE_MEASUREGRID_GRAY")
        
        #obj_data = read_obj_file(obj_file_path)
        #log_and_print(f'obj_data: {obj_data}')
        #write_obj_file(obj_data, obj_file_path)
        
        #obj_data = relocate_vertex_data(obj_data)
        
        #obj_data = weld_vertices(obj_data)
        #write_obj_file(obj_data, obj_file_path)
        
        # Same vertices weld
        optimize_vertexes(obj_file_path, True)
        
        #rewrite_obj_data = read_obj_file(obj_file_path)
        #write_obj_file(rewrite_obj_data, obj_file_path)
        
        #find_smoothed_vertices(obj_file_path)
        
        ucx_content = ucx_generation(vmf_content, vmf_path, default_units_scale)
        append_cls_data(obj_file_path, ucx_content)
        
        merge_and_filter_objects_by_material_inplace(obj_file_path, materials_to_remove=None)
        #optimize_vertexes(obj_cls_file_path, False)
        
        #append_cls_data(obj_cls_file_path, ucx_content)
        
        
        #sg_to_vn(obj_file_path)
        prepend_description_to_obj_file(obj_file_path, obj_description)

try:
    if __name__ == '__main__':
        main()
        log_and_print("-" * 50)
        log_and_print(f'Done!')
except Exception as e:
    import traceback
    print(f"An error occurred: {e}")
    print(traceback.format_exc())
finally:
    log_file.close()
    #input("\nPress Enter to continue...")