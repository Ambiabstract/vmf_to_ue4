import unreal
import os
import sys
import subprocess

# MAIN SETTINGS

gameconfig_path = r"C:\Program Files (x86)\Steam\steamapps\common\Half-Life 2\bin\hammerplusplus\hammerplusplus_gameconfig.txt" # used by hammer
game_name = r"Atmus"            # game name, used by hammer per project
default_units_scale = 2         # hammer units to unreal centimeters, 128 hu wall height -> 256 cm w.h.
lightmap_resolution = 256       # дефолт - 64, надо будет брать из люкселя наверное
use_complex_cls_for_solid_geometry = False # player clip brushes ingored if true =(((( also makes bad performance((99
solid_geometry_materials_create = False

# REIMPORT BOOLS

rebuild_solid_geometry_obj = True
reimport_solid_geometry = True
reimport_lights = True
regenerate_textures = True
reimport_materials = True

# GLOBAL VARS

ue_project_path = unreal.SystemLibrary.get_project_directory()
ue_project_content_path = ue_project_path+"content"
editor_level_lib = unreal.EditorLevelLibrary
current_level = unreal.EditorLevelLibrary.get_editor_world()
current_level_path = current_level.get_path_name()
current_level_name = str(current_level).split('/')[-1].split('.')[0]

# FUNCTIONS

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

def find_vmf_file(gamedir_path, current_level_name):
    # Полные пути к директориям для поиска
    mapsrc_path = os.path.join(gamedir_path, 'mapsrc')
    maps_path = os.path.join(gamedir_path, 'maps')
    
    # Функция для поиска файла в директории и поддиректориях
    def search_file(directory, filename):
        for root, dirs, files in os.walk(directory):
            if filename in files:
                return os.path.join(root, filename)
        return None
    
    # Имя файла для поиска
    vmf_filename = f"{current_level_name}.vmf"
    
    # Поиск в папке mapsrc
    result = search_file(mapsrc_path, vmf_filename)
    if result is not None:
        return result
    
    # Поиск в папке maps, если файл не найден в mapsrc
    return search_file(maps_path, vmf_filename)

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

def set_lightmap_resolution(solid_geometry_subfolder_path, new_resolution):
    # Получаем редакторский ассет в Unreal
    asset_registry = unreal.AssetRegistryHelpers.get_asset_registry()

    # Получаем все ассеты в указанной папке
    assets = asset_registry.get_assets_by_path(solid_geometry_subfolder_path, recursive=True)

    # Проходим по всем ассетам
    for asset in assets:
        # Загружаем ассет
        asset_data = asset.get_asset()
        
        # Проверяем, является ли ассет статическим мешем
        if isinstance(asset_data, unreal.StaticMesh):
            static_mesh = asset_data
            
            # Устанавливаем новое разрешение light map в общих настройках
            static_mesh.set_editor_property('light_map_resolution', new_resolution)
            
            # Отмечаем меш как изменённый
            static_mesh.modify()
            
            # Сохраняем изменения
            unreal.EditorAssetLibrary.save_asset(static_mesh.get_path_name())
            print(f'Light map resolution for {static_mesh.get_name()} set to {new_resolution}')

def set_collision_complexity_comp_as_simple(solid_geometry_subfolder_path):
    # Получаем редакторский ассет в Unreal
    asset_registry = unreal.AssetRegistryHelpers.get_asset_registry()

    # Получаем все ассеты в указанной папке
    assets = asset_registry.get_assets_by_path(solid_geometry_subfolder_path, recursive=True)

    # Проходим по всем ассетам
    for asset in assets:
        # Загружаем ассет
        asset_data = asset.get_asset()
        
        # Проверяем, является ли ассет статическим мешем
        if isinstance(asset_data, unreal.StaticMesh):
            static_mesh = asset_data

            # Получаем BodySetup и устанавливаем Collision Complexity
            body_setup = static_mesh.get_editor_property('body_setup')
            if body_setup:
                body_setup.set_editor_property('collision_trace_flag', unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
                
                # Отмечаем меш как изменённый
                static_mesh.modify()
                
                # Сохраняем изменения
                unreal.EditorAssetLibrary.save_asset(static_mesh.get_path_name())
                print(f'Collision complexity for {static_mesh.get_name()} set to Use Complex Collision As Simple')
            else:
                print(f'No BodySetup found for {static_mesh.get_name()}')


def import_obj_as_static_mesh(solid_geometry_subfolder_path, obj_path, lightmap_resolution):    
    # Удаление старых ассетов основной геометрии уровня из контента
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
    import_settings.import_materials = solid_geometry_materials_create
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

def sub_vmf_to_ue4_tga_generation(gamedir_path, vmf_file_path):
    # Path to the Python script to run
    script_path = os.path.dirname(os.path.abspath(__file__))+"/subscripts/vmf_to_ue4_tga_generation.py"
    print(script_path)
    
    args = [str(gamedir_path), str(vmf_file_path)]

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
    
# Function for extracting solid blocks from VMF
def extract_entities_from_vmf(vmf_content):
    entity_start_indices = [m.start() for m in re.finditer(r'entity\s*{\s*"id"\s*"', vmf_content)]
    entities = [extract_block_content(vmf_content, start) for start in solid_start_indices]
    
    check_blocks_info(solid_blocks, "entity", "VMF")
    log_and_print(f"entities:\n{entities}")
    
    return entities

import re

def extract_entities_with_regex(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()
    
    pattern = re.compile(r'entity\s*\{.*?\}', re.DOTALL)
    matches = pattern.findall(content)
    
    entities = []
    light_classes = {"light", "light_spot", "light_environment", "light_dynamic"}
    
    for match in matches:
        entity_dict = {}
        lines = match.split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('"') and '"' in line[1:]:
                key, value = line.split('" "', 1)
                key = key.strip('"')
                value = value.strip('"')
                entity_dict[key] = value
        if 'classname' in entity_dict and entity_dict['classname'] in light_classes:
            entities.append(entity_dict)
    
    return entities

def create_advanced_light_old(location, color=(1, 1, 1), intensity=1000, light_radius=1000, attenuation_radius=5000, temperature=6500, soft_source_radius=200, falloff_exponent=2.0, mobility=unreal.ComponentMobility.STATIC):
    # Создание актора света в мире
    light_actor = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.PointLight, location)
    light_component = light_actor.get_component_by_class(unreal.PointLightComponent)
    
    # Установка параметров света
    light_color = unreal.LinearColor(color[0], color[1], color[2], 1.0)
    light_component.set_light_color(light_color)
    light_component.set_intensity(intensity)
    light_component.set_source_radius(light_radius)
    light_component.set_soft_source_radius(soft_source_radius)
    light_component.set_attenuation_radius(attenuation_radius)
    light_component.set_light_falloff_exponent(falloff_exponent)
    light_component.set_temperature(temperature)
    light_component.set_use_temperature(True)

    # Установка типа Mobility для светового компонента
    light_component.set_mobility(mobility)

    return light_actor

def create_advanced_light(entity):
    classname = entity.get('classname', 'light')
    entity_id = entity.get('id', 'unknown')
    
    # Парсинг данных из entity
    location_str = entity.get('origin', '0 0 0')
    location_values = list(map(float, location_str.split()))
    location = unreal.Vector(*map(float, location_str.split()))
    #location *= unreal.Vector(*map(float, location_str.split()))
    # Меняем местами оси и умножаем на default_units_scale
    location = unreal.Vector(location_values[0] * default_units_scale, 
                             location_values[1] * -default_units_scale, 
                             location_values[2] * default_units_scale)
    #print(f"!!! LIGHT LOCATION: {location}")
    
    color_str = entity.get('_light', '255 255 255 200')
    color_values = list(map(float, color_str.split()))
    color = tuple(v / 255.0 for v in color_values[:3])  # Normalize RGB values to 0-1
    intensity = color_values[3] if len(color_values) > 3 else 1000
    if classname == 'light_environment':
        intensity *= 1/16
    else:
        intensity *= 2 * default_units_scale * default_units_scale
        intensity **= 1.25
    #print(f"!!! LIGHT INTENCITY: {intensity}")
    
    angles_str = entity.get('angles', '0 0 0')
    rotation_values = list(map(float, angles_str.split()))
    rotation = unreal.Rotator(*map(float, angles_str.split()))
    rotation = unreal.Rotator(rotation_values[2], 
                             rotation_values[0], 
                             rotation_values[1] * -1)
                             
    if classname == 'light':
        mobility = unreal.ComponentMobility.STATIC
    if classname == 'light_spot':
        mobility = unreal.ComponentMobility.STATIC
        #mobility = unreal.ComponentMobility.STATIONARY
        #mobility = unreal.ComponentMobility.MOVABLE
    if classname == 'light_environment':
        mobility = unreal.ComponentMobility.MOVABLE
    if classname == 'light_dynamic':
        mobility = unreal.ComponentMobility.MOVABLE

    #mobility = unreal.ComponentMobility.STATIC        
    #mobility = unreal.ComponentMobility.MOVABLE
    #mobility = unreal.ComponentMobility.STATIONARY            
    
    # Соответствие типов света
    light_class = {
        'light': unreal.PointLight,
        'light_spot': unreal.SpotLight,
        'light_environment': unreal.DirectionalLight,
        'light_dynamic': unreal.SpotLight
    }.get(classname, unreal.PointLight)
    
    # Создание актора света в мире
    light_actor = unreal.EditorLevelLibrary.spawn_actor_from_class(light_class, location, rotation)
    if not light_actor:
        unreal.log_warning(f"Не удалось создать актор света для entity: {entity}")
        return None
    
    # Установка имени актора
    actor_label = f"{classname}_{entity_id}"
    light_actor.set_actor_label(actor_label)
    light_actor.set_folder_path("_generated/entities/lights")
    
    # Получение компонента света
    if light_class == unreal.PointLight:
        light_component = light_actor.get_component_by_class(unreal.PointLightComponent)
    elif light_class == unreal.SpotLight:
        light_component = light_actor.get_component_by_class(unreal.SpotLightComponent)
    elif light_class == unreal.DirectionalLight:
        light_component = light_actor.get_component_by_class(unreal.DirectionalLightComponent)
    else:
        light_component = None
    
    if not light_component:
        unreal.log_warning(f"Не удалось найти компонент света для актора: {light_actor.get_name()}")
        return None
    
    # Установка параметров света
    light_color = unreal.LinearColor(color[0], color[1], color[2], 1.0)
    light_component.set_light_color(light_color)  # Изменение метода установки цвета
    light_component.set_editor_property('intensity', intensity)
    
    #if classname == 'light':
    #    light_component.set_editor_property('indirect_lighting_intensity', 6.0)  # Default value
    #if classname == 'light_spot':
    #    light_component.set_editor_property('indirect_lighting_intensity', 6.0)  # Default value
    #if classname == 'light_environment':
    #    light_component.set_editor_property('indirect_lighting_intensity', 6.0)  # Default value
    if classname == 'light_dynamic':
        light_component.set_editor_property('indirect_lighting_intensity', 0.0)  # Default value
    else:
        light_component.set_editor_property('indirect_lighting_intensity', 64.0)  # Default value
    
    # Установка специфичных для компонента свойств
    if isinstance(light_component, unreal.PointLightComponent) or isinstance(light_component, unreal.SpotLightComponent):
        light_component.set_editor_property('source_radius', 16)  # Default values
        light_component.set_editor_property('soft_source_radius', 128)  # Default values
        light_component.set_editor_property('attenuation_radius', 2048)  # Default values
        light_component.set_editor_property('light_falloff_exponent', 1.0)  # Default values
    
    if classname == 'light_spot':
        outer_cone_angle = entity.get('_cone', '45')
        inner_cone_angle = entity.get('_inner_cone', '30')
        #print(f"!!! INNER CONE: {inner_cone_angle}")
        #print(f"!!! OUTER CONE: {outer_cone_angle}")
        light_component.set_editor_property('inner_cone_angle', float(inner_cone_angle))
        light_component.set_editor_property('outer_cone_angle', float(outer_cone_angle))
    
    #{
    #    "id": "751",
    #    "classname": "light_spot",
    #    "_cone": "45",
    #    "_constant_attn": "0",
    #    "_distance": "0",
    #    "_exponent": "1",
    #    "_fifty_percent_distance": "0",
    #    "_hardfalloff": "0",
    #    "_inner_cone": "30",
    #    "_light": "255 255 255 200",
    #    "_lightHDR": "-1 -1 -1 1",
    #    "_lightscaleHDR": "1",
    #    "_linear_attn": "0",
    #    "_quadratic_attn": "1",
    #    "_zero_percent_distance": "0",
    #    "angles": "-90 0 0",
    #    "pitch": "-90",
    #    "style": "0",
    #    "targetname": "light_default",
    #    "origin": "-256 -640 -32",
    #    "color": "220 30 220",
    #    "visgroupshown": "1",
    #    "visgroupautoshown": "1",
    #    "logicalpos": "[0 4000]"
    #},
    
    
    # Установка типа Mobility для светового компонента
    light_component.set_editor_property('mobility', mobility)

    return light_actor

def place_lights(entities):
    for entity in entities:
        create_advanced_light(entity)

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

def import_tga_texture(vtf_path):
    tga_path = vtf_path.replace('.vtf', '.tga')
    
    # Проверяем, что путь начинается с "materials"
    materials_index = tga_path.lower().find("materials")
    if materials_index == -1:
        unreal.log_error("Путь не содержит папки 'materials': {}".format(tga_path))
        return

    # Получаем относительный путь от папки "materials"
    relative_path = tga_path[materials_index:]

    # Формируем путь для импортированной текстуры в проекте
    asset_path = "/Game/" + relative_path.replace("\\", "/").replace(".tga", "")

    # Настраиваем опции импорта
    task = unreal.AssetImportTask()
    task.filename = tga_path
    task.destination_path = asset_path.rsplit("/", 1)[0]
    task.destination_name = asset_path.rsplit("/", 1)[-1]
    task.replace_existing = True
    task.automated = True
    task.save = True

    # Импортируем текстуру
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])

    if task.imported_object_paths:
        unreal.log("Успешно импортировано: {}".format(task.imported_object_paths[0]))
    else:
        unreal.log_error("Не удалось импортировать текстуру: {}".format(tga_path))

def create_material_with_texture(material_path, texture_path):
    # Преобразование пути к материалу
    material_path_parts = material_path.split('/')
    asset_name = material_path_parts[-1]
    asset_path = f"/Game/materials/{material_path}"

    # Получение редактора активов
    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()

    # Создание нового материала
    material_factory = unreal.MaterialFactoryNew()
    material = asset_tools.create_asset(asset_name, asset_path.rsplit('/', 1)[0], None, material_factory)

    if not material:
        unreal.log_error(f"Не удалось создать материал по пути: {asset_path}")
        return

    # Загрузка текстуры
    texture = unreal.EditorAssetLibrary.load_asset(texture_path)
    if not texture:
        unreal.log_error(f"Не удалось загрузить текстуру по пути: {texture_path}")
        return

    # Создание выражения для текстуры
    texture_expression = unreal.MaterialExpressionTextureSample()
    texture_expression.texture = texture

    # Добавление выражения в материал
    material_expressions = material.get_editor_property('expressions')
    material_expressions.append(texture_expression)
    material.set_editor_property('expressions', material_expressions)

    # Присоединение выражения к базовому цвету материала
    unreal.MaterialEditingLibrary.connect_material_property(
        texture_expression, 'RGB', unreal.MaterialProperty.MP_BASE_COLOR
    )

    # Сохранение материала
    unreal.EditorAssetLibrary.save_asset(material.get_path_name())
    unreal.log(f"Материал создан и сохранен по пути: {material.get_path_name()}")

def import_materials(vmf_path, gameinfo_path):
    materials_path = gameinfo_path #temp
    vmt_files = find_vmt_files(vmf_path, materials_path)
    for material, vmt_path in vmt_files.items():
        #material_name = material.rsplit('/', 1)[-1]
        #print(f"material_name: {material_name}")
        
        vtf_paths = find_vtf_paths(vmt_path, materials_path)
        for vtf_path in vtf_paths:
            if os.path.isfile(vtf_path):
                import_tga_texture(vtf_path)
                #tga_path = vtf_path.replace('.vtf', '.tga')
                #create_material_with_texture(material, texture_path)
            else:
                print(f"VTF file not found: {vtf_path}")
        
        

def main():
    # Preparation
    print(f"\n\n|------------------|\n")
    print(f"\n\n|VMF TO UE4 STARTED|\n")
    print(f"\n\n|------------------|--------------------------------------------------------------------------------\n")
    print(f"ue_project_path:\t\t{ue_project_path}")
    print(f"current_level_name:\t\t{current_level_name}")
    gamedir_path, default_texture_scale = parse_game_config(gameconfig_path, game_name)
    print(f"gamedir_path:\t\t\t{gamedir_path}")
    print(f"default_texture_scale:\t{default_texture_scale}")
    vmf_file_path = find_vmf_file(gamedir_path, current_level_name)
    print(f"vmf_file_path:\t\t\t{vmf_file_path}")
    current_level_files_path = create_level_files_folder()
    
    # Генерация OBJ основной геометрии уровня
    if rebuild_solid_geometry_obj == True:
        print("-" * 100)
        print(f"Starting VMF to OBJ conversion...")
        sub_vmf_to_ue4_obj_generation(gamedir_path, vmf_file_path, default_units_scale, default_texture_scale)
        
    obj_path = os.path.splitext(vmf_file_path)[0] + '.obj'
    print(f"obj_path:\t\t\t{obj_path}")
    
    solid_geometry_subfolder_path = current_level_files_path + "/solid_geometry"
    
    # Импорт и расстановка основной геометрии уровня
    if reimport_solid_geometry == True:
        print("-" * 100)
        print(f"Starting OBJ import and Static Meshes placing...")
        import_obj_as_static_mesh(solid_geometry_subfolder_path, obj_path, lightmap_resolution)
        set_lightmap_resolution(solid_geometry_subfolder_path, lightmap_resolution)
        if use_complex_cls_for_solid_geometry == True:
            set_collision_complexity_comp_as_simple(solid_geometry_subfolder_path)
        delete_actors_from_lvl_outliner_folder(outliner_folder="_generated/solid_geometry")
        place_static_meshes_to_lvl(solid_geometry_subfolder_path, outliner_folder="_generated/solid_geometry")

    # Импорт и расстановка фанк детейлов
    # Импорт и расстановка инстансов
    # Импорт и расстановка дисплейсментов
    
    # Импорт и расстановка источников освещения
    if reimport_lights == True:
        delete_actors_from_lvl_outliner_folder(outliner_folder="_generated/entities/lights")
        light_entities = extract_entities_with_regex(vmf_file_path)
        place_lights(light_entities)

    # Расстановка статик пропов включая те что в инстансах
    
    # Генерация тга текстур
    if regenerate_textures == True:
        sub_vmf_to_ue4_tga_generation(gamedir_path, vmf_file_path)
    if reimport_materials == True:
        import_materials(vmf_file_path, gamedir_path)


try:
    if __name__ == '__main__':
        main()
except Exception as e:
    import traceback
    print(f"An error occurred: {e}")
    print(traceback.format_exc())
#finally:
#    input("\nPress Enter to exit...")
