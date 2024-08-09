import os
import sys
import subprocess
import re

# MAIN SETTINGS

gameconfig_path = r"C:\Program Files (x86)\Steam\steamapps\common\Half-Life 2\bin\hammerplusplus\hammerplusplus_gameconfig.txt" # used by hammer
game_name = r"Atmus"            # game name, used by hammer per project
default_units_scale = 2         # hammer units to unreal centimeters, 128 hu wall height -> 256 cm w.h.

# GLOBAL VARS

#ue_project_path = unreal.SystemLibrary.get_project_directory()
#ue_project_content_path = ue_project_path+"content"
#editor_level_lib = unreal.EditorLevelLibrary
#current_level = unreal.EditorLevelLibrary.get_editor_world()
#current_level_path = current_level.get_path_name()
#current_level_name = str(current_level).split('/')[-1].split('.')[0]

# FUNCTIONS

def log_and_print(data):
    print(data)
    #log_file.write(data + '\n')

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

def parse_game_config(gameconfig_path, game_name):
    with open(gameconfig_path, 'r', encoding='utf-8') as file:
        content = file.read()

    # Поиск начала блока конфигурации для заданной игры
    game_start_index = content.find(f'"{game_name}"')
    if game_start_index == -1:
        return None, None  # Игра Not foundа

    # Использование функции find_brace_indices для определения начала и конца блока игры
    open_index, close_index = find_brace_indices(content, game_start_index)

    if open_index == -1 or close_index == -1:
        return None, None  # Не удалось найти блок конфигурации

    # Срез блока конфигурации игры
    game_block = content[open_index:close_index]

    # Извлечение gamedir
    gamedir_start = game_block.find('"gamedir"\t\t"')
    gamedir_end = game_block.find('"', gamedir_start + 12)
    gamedir = game_block[gamedir_start + 12:gamedir_end] if gamedir_start != -1 else "Not found"

    # Извлечение defaulttexturescale
    scale_start = game_block.find('"defaulttexturescale"\t\t"') + len('"defaulttexturescale"\t\t"')
    if scale_start == -1 + len('"defaulttexturescale"\t\t"'):
        return "Not found"

    scale_end = game_block.find('"', scale_start)
    if scale_end == -1:
        return "Not found"
    
    defaulttexturescale_str = game_block[scale_start:scale_end].strip()
    try:
        defaulttexturescale = float(defaulttexturescale_str)
    except ValueError:
        return "Not found"

    return gamedir, defaulttexturescale

def delete_all_files_in_folder(folder_path, recursive=True, include_folder=False):
    # Получение списка всех ассетов в указанной папке
    asset_paths = unreal.EditorAssetLibrary.list_assets(folder_path, recursive, include_folder)
    
    # Удаление каждого ассета в списке
    for asset_path in asset_paths:
        unreal.EditorAssetLibrary.delete_asset(asset_path)

def create_level_files_folder():
    # Строим путь для новой папки рядом с файлом уровня
    new_folder_path = current_level_path.rsplit('/', 1)[0] + "/" + current_level_name + "_files"
    
    # Создаём папку
    if not unreal.EditorAssetLibrary.does_directory_exist(new_folder_path):
        unreal.EditorAssetLibrary.make_directory(new_folder_path)
        print("Level assets folder:\t{}".format(new_folder_path))
    else:
        print("Level assets folder:\t{}".format(new_folder_path))
    return new_folder_path

def save_current_level():
    # Попытка вызова функции save_current_level
    try:
        unreal.EditorLevelLibrary.save_current_level()
        unreal.log("Уровень успешно сохранен")
    except AttributeError as e:
        unreal.log_error("Ошибка: Функция save_current_level() не доступна - " + str(e))

def delete_actors_from_lvl_outliner_folder(outliner_folder="_generated"):
    # Получаем все акторы на текущем уровне
    all_actors = unreal.EditorLevelLibrary.get_all_level_actors()
    
    # Перебираем акторов и удаляем тех, кто находится в указанной папке
    for actor in all_actors:
        if actor.get_folder_path() == outliner_folder:
            unreal.EditorLevelLibrary.destroy_actor(actor)
    save_current_level()

def place_static_meshes_to_lvl(static_meshes_folder, outliner_folder="_generated"):
    # Получаем список всех статик мешей в папке
    static_meshes = unreal.EditorAssetLibrary.list_assets(static_meshes_folder, recursive=False, include_folder=True)
    
    # Перебираем найденные меши и создаем для каждого актор на уровне
    for mesh_path in static_meshes:
        mesh_asset = unreal.load_asset(mesh_path)
        if isinstance(mesh_asset, unreal.StaticMesh):
            # Создаем актор с этим статик мешем на уровне
            actor = unreal.EditorLevelLibrary.spawn_actor_from_object(mesh_asset, unreal.Vector(0,0,0))
            # Устанавливаем папку в иерархии уровня
            actor.set_folder_path(outliner_folder)
    save_current_level()

def import_obj_as_static_mesh(solid_geometry_subfolder_path, obj_path):
    # Удаление старых ассетов из слоя уровня, сохранение уровня
    # <сделать>
    
    # Удаление старых ассетов основной геометрии уровня
    delete_all_files_in_folder(solid_geometry_subfolder_path, recursive=True, include_folder=False)
    
    # Создание объекта для настроек импорта
    import_settings = unreal.FbxImportUI()
    
    # Настройки для статического меша
    import_settings.import_mesh = True
    import_settings.mesh_type_to_import = unreal.FBXImportType.FBXIT_STATIC_MESH
    import_settings.static_mesh_import_data.combine_meshes = False
    import_settings.static_mesh_import_data.generate_lightmap_u_vs = True
    import_settings.static_mesh_import_data.auto_generate_collision = False
    import_settings.static_mesh_import_data.remove_degenerates = True
    #import_settings.static_mesh_import_data.convert_scene = False
    #import_settings.static_mesh_import_data.convert_scene_unit = False
    import_settings.static_mesh_import_data.normal_import_method = unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS_AND_TANGENTS
    
    # Отключение импорта материалов
    import_settings.import_materials = False
    import_settings.import_textures = False
    
    # Создание задачи импорта
    task = unreal.AssetImportTask()
    task.filename = obj_path
    task.destination_path = solid_geometry_subfolder_path
    task.options = import_settings
    task.replace_existing = True
    task.automated = True
    task.save = True
    
    # Импорт файла
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    
    # Проверка результатов
    if task.imported_object_paths:
        print("Import successful: ", task.imported_object_paths)
    else:
        print("Import failed")

def sub_vmf_to_ue4_obj_generation(gamedir_path, vmf_file_path, default_units_scale, default_texture_scale):
    # Path to the Python script to run
    script_path = os.path.dirname(os.path.abspath(__file__))+"/subscripts/vmf_to_ue4_obj_generation.py"
    print(script_path)
    
    args = [str(gamedir_path), str(vmf_file_path), str(default_units_scale), str(default_texture_scale)]

    # Running a script and waiting for it to complete
    result = subprocess.run(['python', script_path] + args, capture_output=False, text=True)
    if result.returncode == 0:
        print("Script executed successfully")
        print("Script output:", result.stdout)
    else:
        print("Error executing script")
        print("Error code:", result.returncode)
        print("Error:", result.stderr)
        return

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

def write_objects_to_file(filename, objects):
    """
    Записывает список объектов в файл в удобочитаемом формате.

    Args:
    filename (str): Имя файла, в который будет произведена запись.
    objects (list of dict): Список объектов для записи.
    """
    try:
        with open(filename, 'w', encoding='utf-8') as file:
            for obj in objects:
                file.write(f"{obj}\n")
            file.write('\n')
    except Exception as e:
        print(f"Произошла ошибка при записи в файл: {e}")

# Function for extracting solid blocks from VMF
def extract_entities_from_vmf(vmf_content):
    entity_start_indices = [m.start() for m in re.finditer(r'entity\s*{\s*"id"\s*"', vmf_content)]
    #write_objects_to_file("entity_start_indices.json", entity_start_indices)
    entities = [extract_block_content(vmf_content, start) for start in entity_start_indices]
    
    lights_start_indices = [m.start() for m in re.finditer(r'entity\s*{\s*"id"\s*"\s*"classname"\s*"', vmf_content)]
    #lights = [extract_block_content(vmf_content, start) for start in lights_start_indices]
    
    # "classname" "light"
    # "classname" "light_spot"
    # "classname" "light_environment"
    
    write_objects_to_file("lights_start_indices.txt", lights_start_indices)
    
    #check_blocks_info(entities, "entity", "VMF")
    
    return entities

def main():
    # Preparation
    #print(f"ue_project_path:\t\t{ue_project_path}")
    #print(f"current_level_name:\t\t{current_level_name}")
    gamedir_path, default_texture_scale = parse_game_config(gameconfig_path, game_name)
    print(f"gamedir_path:\t\t\t{gamedir_path}")
    print(f"default_texture_scale:\t{default_texture_scale}")
    vmf_file_path = r"C:\Program Files (x86)\Steam\steamapps\sourcemods\atmus\maps\light_test_01a.vmf"
    print(f"vmf_file_path:\t\t\t{vmf_file_path}")
    
    # Импорт и расстановка фанк детейлов
    # Импорт и расстановка инстансов
    # Импорт и расстановка дисплейсментов
    
    # Импорт и расстановка источников освещения
    with open(vmf_file_path, 'r') as f:
            vmf_content = f.read()
    entities = extract_entities_from_vmf(vmf_content)
    #log_and_print(f"entities:\n{entities}")
    #test_light_file = r"C:\Users\Ambia\Desktop\test_light_file.txt"
    
    #write_objects_to_file("test_light_file.json", entities)
    
    #test_light_location = unreal.Vector(0, 0, 0)
    #dynamic_light = create_advanced_light(test_light_location, color=(0.5, 0.5, 1), intensity=1500, mobility=unreal.ComponentMobility.MOVABLE)

    
    # Расстановка статик пропов включая те что в инстансах
    
    

try:
    if __name__ == '__main__':
        main()
except Exception as e:
    import traceback
    print(f"An error occurred: {e}")
    print(traceback.format_exc())
finally:
    input("\nPress Enter to exit...")
