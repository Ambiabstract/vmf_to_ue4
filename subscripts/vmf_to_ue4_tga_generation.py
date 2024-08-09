import re
import os
import sys
import numpy as np
from PIL import Image
import struct
import subprocess

vtfcmd_exe_path = r"C:\Program Files\Nem's Tools\VTFEdit\VTFCmd.exe"

# Log file
log_file = open(f"{os.path.splitext(os.path.basename(sys.argv[0]))[0]}_log.txt", 'w', encoding='utf-8')

# Func to log and print something
def log_and_print(data):
    print(data)
    log_file.write(data + '\n')

# Define the VTF image formats
VTF_IMAGE_FORMATS = {
    0: 'RGBA8888',
    1: 'ABGR8888',
    2: 'RGB888',
    3: 'BGR888',
    4: 'RGB565',
    5: 'I8',
    6: 'IA88',
    7: 'P8',
    8: 'A8',
    9: 'RGB888_BLUESCREEN',
    10: 'BGR888_BLUESCREEN',
    11: 'ARGB8888',
    12: 'BGRA8888',
    13: 'DXT1',
    14: 'DXT3',
    15: 'DXT5',
    # Add other formats as needed
}

def decompress_dxt1(data, width, height):
    def unpack_rgb565(rgb):
        r = (rgb >> 11) & 0x1f
        g = (rgb >> 5) & 0x3f
        b = rgb & 0x1f
        return (r << 3, g << 2, b << 3, 255)

    output = np.zeros((height, width, 4), dtype=np.uint8)
    block_count = (width // 4) * (height // 4)
    block_size = 8  # DXT1 block size in bytes

    for i in range(block_count):
        x = (i % (width // 4)) * 4
        y = (i // (width // 4)) * 4
        block = data[i * block_size:(i + 1) * block_size]
        color0, color1 = struct.unpack('<HH', block[:4])
        bits = struct.unpack('<I', block[4:])[0]
        colors = [unpack_rgb565(color0), unpack_rgb565(color1)]
        if color0 > color1:
            colors.append(tuple([(2 * c0 + c1) // 3 for c0, c1 in zip(colors[0], colors[1])]))
            colors.append(tuple([(c0 + 2 * c1) // 3 for c0, c1 in zip(colors[0], colors[1])]))
        else:
            colors.append(tuple([(c0 + c1) // 2 for c0, c1 in zip(colors[0], colors[1])]))
            colors.append((0, 0, 0, 255))
        
        for j in range(4):
            for k in range(4):
                index = (bits >> (2 * (4 * j + k))) & 0x03
                output[y + j, x + k] = colors[index]

    return output.tobytes()

def decompress_dxt5(data, width, height):
    def unpack_rgb565(rgb):
        r = (rgb >> 11) & 0x1f
        g = (rgb >> 5) & 0x3f
        b = rgb & 0x1f
        return (r << 3, g << 2, b << 3)

    def get_interpolated_alpha(alpha0, alpha1):
        alphas = [alpha0, alpha1]
        if alpha0 > alpha1:
            for i in range(1, 7):
                alphas.append(((7 - i) * alpha0 + i * alpha1) // 7)
        else:
            for i in range(1, 5):
                alphas.append(((5 - i) * alpha0 + i * alpha1) // 5)
            alphas.append(0)
            alphas.append(255)
        return alphas

    output = np.zeros((height, width, 4), dtype=np.uint8)
    block_count = (width // 4) * (height // 4)
    block_size = 16  # DXT5 block size in bytes

    for i in range(block_count):
        x = (i % (width // 4)) * 4
        y = (i // (width // 4)) * 4
        block = data[i * block_size:(i + 1) * block_size]

        alpha0, alpha1 = struct.unpack('<BB', block[:2])
        alpha_indices = struct.unpack('<Q', block[:6] + b'\x00\x00')[0]
        color0, color1 = struct.unpack('<HH', block[8:12])
        bits = struct.unpack('<I', block[12:])[0]

        alphas = get_interpolated_alpha(alpha0, alpha1)
        colors = [unpack_rgb565(color0) + (255,), unpack_rgb565(color1) + (255,)]
        if color0 > color1:
            colors.append(tuple([(2 * c0 + c1) // 3 for c0, c1 in zip(colors[0], colors[1])]))
            colors.append(tuple([(c0 + 2 * c1) // 3 for c0, c1 in zip(colors[0], colors[1])]))
        else:
            colors.append(tuple([(c0 + c1) // 2 for c0, c1 in zip(colors[0], colors[1])]))
            colors.append((0, 0, 0, 0))

        for j in range(4):
            for k in range(4):
                color_index = (bits >> (2 * (4 * j + k))) & 0x03
                alpha_index = (alpha_indices >> (3 * (4 * j + k))) & 0x07
                color = colors[color_index]
                alpha = alphas[alpha_index]
                output[y + j, x + k] = (*color[:3], alpha)

    return output.tobytes()

def read_vtf_header(file_path):
    """
    Reads the header of a VTF file and returns the relevant information.
    """
    with open(file_path, 'rb') as file:
        header = file.read(80)
        if len(header) < 80:
            raise ValueError("File too small to be a valid VTF file.")
        
        #print(f"Raw header bytes: {header[:64]}")
        
        # Extract signature and version
        signature, version_major, version_minor = struct.unpack('<4sII', header[:12])
        
        # Extract header size
        header_size = struct.unpack('<I', header[12:16])[0]
        
        # Extract width and height
        width, height = struct.unpack('<HH', header[16:20])
        
        # Extract flags and frames
        flags, frames = struct.unpack('<IH', header[20:26])
        
        # Extract first frame
        first_frame = struct.unpack('<H', header[26:28])[0]
        
        # Extract padding0 (skip 4 bytes)
        padding0 = struct.unpack('<4B', header[28:32])
        
        # Extract reflectivity (12 bytes)
        reflectivity = struct.unpack('<3f', header[32:44])
        
        # Extract padding1
        padding1 = struct.unpack('<I', header[44:48])[0]
        
        # Extract bumpmap scale
        bumpmap_scale = struct.unpack('<f', header[48:52])[0]
        
        # Extract image format code
        image_format_code = struct.unpack('<I', header[52:56])[0]
        
        # Extract mipmap count
        mipmap_count = struct.unpack('<B', header[56:57])[0]
        
        # Extract low res image format, width and height
        low_res_image_format = struct.unpack('<B', header[57:58])[0]
        low_res_image_width = struct.unpack('<B', header[58:59])[0]
        low_res_image_height = struct.unpack('<B', header[59:60])[0]
        
        # Extract depth
        if version_major >= 7 and version_minor >= 2:
            depth = struct.unpack('<B', header[63:64])[0]
        else:
            depth = 1
        
        # Extract number of resources
        if version_major >= 7 and version_minor >= 3:
            num_resources = struct.unpack('<I', header[75:79])[0]
        else:
            num_resources = 0
        
        # Print each extracted field for debugging
        print(f"Signature: {signature}")
        print(f"Version Major: {version_major}")
        print(f"Version Minor: {version_minor}")
        print(f"Header Size: {header_size}")
        print(f"Width: {width}")
        print(f"Height: {height}")
        print(f"Flags: {flags}")
        print(f"Frames: {frames}")
        print(f"First Frame: {first_frame}")
        print(f"Padding0: {padding0}")
        print(f"Reflectivity: {reflectivity}")
        print(f"Padding1: {padding1}")
        print(f"Bumpmap Scale: {bumpmap_scale}")
        print(f"Image Format Code: {image_format_code}")
        print(f"Mipmap Count: {mipmap_count}")
        print(f"Low Res Image Format: {low_res_image_format}")
        print(f"Low Res Image Width: {low_res_image_width}")
        print(f"Low Res Image Height: {low_res_image_height}")
        print(f"Depth: {depth}")
        print(f"Number of Resources: {num_resources}")

        image_format = VTF_IMAGE_FORMATS.get(image_format_code, 'UNKNOWN')

        return {
            'version_major': version_major,
            'version_minor': version_minor,
            'header_size': header_size,
            'width': width,
            'height': height,
            'flags': flags,
            'frames': frames,
            'first_frame': first_frame,
            'padding0': padding0,
            'reflectivity': reflectivity,
            'padding1': padding1,
            'bumpmap_scale': bumpmap_scale,
            'image_format_code': image_format_code,
            'image_format': image_format,
            'mipmap_count': mipmap_count,
            'low_res_image_format': low_res_image_format,
            'low_res_image_width': low_res_image_width,
            'low_res_image_height': low_res_image_height,
            'depth': depth,
            'num_resources': num_resources,
        }

def read_vtf_image_data(file_path, header, mip_level=0):
    """
    Reads the image data from a VTF file based on the format specified in the header.
    """
    width = max(header['width'] >> mip_level, 1)
    height = max(header['height'] >> mip_level, 1)

    block_size = {
        'DXT1': 8,
        'DXT5': 16,
        'BGR888': 3,
        'BGRA8888': 4
    }.get(header['image_format'], 0)

    if block_size == 0:
        raise ValueError(f"Unsupported image format: {header['image_format']}")

    if header['image_format'] in ['DXT1', 'DXT5']:
        block_width = (width + 3) // 4
        block_height = (height + 3) // 4
        image_data_size = block_width * block_height * block_size
    else:
        image_data_size = width * height * block_size

    offset = header['header_size']
    for level in range(mip_level):
        if header['image_format'] in ['DXT1', 'DXT5']:
            block_width = (max(header['width'] >> level, 1) + 3) // 4
            block_height = (max(header['height'] >> level, 1) + 3) // 4
            image_data_size = block_width * block_height * block_size
        else:
            image_data_size = max(header['width'] >> level, 1) * max(header['height'] >> level, 1) * block_size
        offset += image_data_size

    with open(file_path, 'rb') as file:
        file.seek(offset)
        image_data = file.read(image_data_size)

    if header['image_format'] == 'DXT1':
        decompressed_image_data = decompress_dxt1(image_data, width, height)
    elif header['image_format'] == 'DXT5':
        decompressed_image_data = decompress_dxt5(image_data, width, height)
    elif header['image_format'] == 'BGR888':
        decompressed_image_data = b''.join([image_data[i:i+3][::-1] + b'\xff' for i in range(0, len(image_data), 3)])
    elif header['image_format'] == 'BGRA8888':
        decompressed_image_data = b''.join([image_data[i:i+4][2::-1] + image_data[i+3:i+4] for i in range(0, len(image_data), 4)])
    else:
        raise ValueError(f"Unsupported image format: {header['image_format']}")

    return decompressed_image_data

def convert_vtf_to_tga(vtfcmd_exe_path, vtf_path):
    # Проверяем, что файл VTF существует
    if not os.path.isfile(vtf_path):
        print(f"Файл {vtf_path} не найден.")
        return
    
    # Проверяем, что файл VTFCmd.exe существует
    if not os.path.isfile(vtfcmd_exe_path):
        print(f"Файл {vtfcmd_exe_path} не найден.")
        return
    
    # Получаем путь для сохранения TGA
    output_folder = os.path.dirname(vtf_path)
    tga_path = os.path.splitext(vtf_path)[0] + ".tga"
    
    # Формируем команду для вызова VTFCmd.exe
    command = [vtfcmd_exe_path, '-file', vtf_path, '-output', output_folder, '-exportformat', 'tga']
    
    # Запускаем процесс
    try:
        subprocess.run(command, check=True)
        print(f"Файл сохранен как {tga_path}")
    except subprocess.CalledProcessError as e:
        print(f"Произошла ошибка при конвертации: {e}")

def find_vmt_files(vmf_path, materials_path):
    with open(vmf_path, 'r') as vmf_file:
        vmf_content = vmf_file.read()

    material_pattern = r'"material"\s+"([^"]+)"'
    materials = re.findall(material_pattern, vmf_content, re.IGNORECASE)

    vmt_files = {}
    for material in materials:
        mat_file_name = ((material.split("/")[-1]) + ".vmt").lower()
        vmt_path = None
        for root, dirs, files in os.walk(materials_path):
            for file in files:
                if file.lower() == mat_file_name:
                    vmt_path = os.path.join(root, file)
                    break
            if vmt_path:
                break
        if vmt_path:
            vmt_files[material] = vmt_path

    return vmt_files

def find_vtf_paths(vmt_path, materials_path):
    with open(vmt_path, 'r') as file:
        vmt_content = file.read()

    vtf_paths = []

    # Find $basetexture
    vtf_pattern = r'\$basetexture\s+"([^"]+)"'
    vtf_matches = re.findall(vtf_pattern, vmt_content, re.IGNORECASE)
    for vtf_match in vtf_matches:
        vtf_path = os.path.join(materials_path, vtf_match + ".vtf")
        if not os.path.isfile(vtf_path):
            vtf_file_name = ((vtf_match.split("/")[-1]) + ".vtf").lower()
            for root, dirs, files in os.walk(materials_path):
                for file in files:
                    if file.lower() == vtf_file_name:
                        vtf_path = os.path.join(root, file)
                        break
                if os.path.isfile(vtf_path):
                    break
        vtf_paths.append(vtf_path)

    # Find $bumpmap
    vtf_pattern = r'\$bumpmap\s+"([^"]+)"'
    vtf_matches = re.findall(vtf_pattern, vmt_content, re.IGNORECASE)
    for vtf_match in vtf_matches:
        vtf_path = os.path.join(materials_path, vtf_match + ".vtf")
        if not os.path.isfile(vtf_path):
            vtf_file_name = ((vtf_match.split("/")[-1]) + ".vtf").lower()
            for root, dirs, files in os.walk(materials_path):
                for file in files:
                    if file.lower() == vtf_file_name:
                        vtf_path = os.path.join(root, file)
                        break
                if os.path.isfile(vtf_path):
                    break
        vtf_paths.append(vtf_path)

    return vtf_paths

def convert_materials_to_tga(vmf_path, gameinfo_path, mip_level=0):
    materials_path = gameinfo_path #temp
    vmt_files = find_vmt_files(vmf_path, materials_path)
    for material, vmt_path in vmt_files.items():
        vtf_paths = find_vtf_paths(vmt_path, materials_path)
        for vtf_path in vtf_paths:
            if os.path.isfile(vtf_path):
                convert_vtf_to_tga(vtfcmd_exe_path, vtf_path)
            else:
                print(f"VTF file not found: {vtf_path}")

def main():
    log_and_print(f'OBJ PROCESSING STARTED!')
    
    # Assuming the VMF files are dragged onto the script
    gamedir_path, vmf_file_path = sys.argv[1:]
    
    log_and_print(f'gamedir_path: {gamedir_path}')
    log_and_print(f'vmf_file_path: {vmf_file_path}')
    
    # Генерация тга текстур
    convert_materials_to_tga(vmf_file_path, gamedir_path, mip_level=0)

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