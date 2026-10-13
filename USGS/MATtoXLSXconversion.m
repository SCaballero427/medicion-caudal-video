%% Cargar datos
data = load("C:\Users\Sergio\Documents\test_pyorc\USGS\SMC_PIV_results.mat");

%% Obtener la estructura de descripciones
zzVariableDescriptions = data.zzVariableDescriptions;

%% Obtener los nombres de los campos
fields = fieldnames(zzVariableDescriptions);

%% Crear una celda para almacenar Variable y Descripción
dataTable = cell(length(fields), 2);

for k = 1:length(fields)

    % Nombre de la variable (sin el sufijo "_descript")
    variableName = erase(fields{k}, "_descript");

    % Descripción
    description = zzVariableDescriptions.(fields{k});

    % Eliminar saltos de línea para que el Excel sea más limpio
    description = strrep(description, newline, ' ');
    description = strrep(description, sprintf('\n'), ' ');

    % Guardar en la tabla
    dataTable{k,1} = variableName;
    dataTable{k,2} = description;

end

%% Convertir a tabla
T = cell2table(dataTable, ...
    'VariableNames', {'Variable', 'Descripcion'});

%% Guardar en Excel
writetable(T, 'VariableDescriptions.xlsx');

disp('Excel generado correctamente: VariableDescriptions.xlsx');