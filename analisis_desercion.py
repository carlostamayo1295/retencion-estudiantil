import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.ticker import PercentFormatter

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 30)

RAW = Path(__file__).parent / "Data" / "raw" / "datos_estudiantes.csv"
PROCESSED = Path(__file__).parent / "Data" / "processed"
GRAFICOS = PROCESSED / "graficos"

# Valores válidos de cada columna categórica (la forma correcta de escribirlos).
VALIDOS = {
    "programa": ["Administración de Empresas", "Contaduría Pública", "Derecho", "Psicología",
                 "Ingeniería de Sistemas", "Ingeniería Industrial", "Enfermería", "Diseño Gráfico"],
    "jornada": ["Diurna", "Nocturna", "Fin de semana"],
    "genero": ["Femenino", "Masculino"],
    "ciudad_procedencia": ["Bogotá", "Medellín", "Cali", "Bucaramanga", "Rionegro",
                           "Barranquilla", "Otra ciudad"],
}

DECISIONES = []
MOSTRAR_GRAFICOS = True


def registrar(paso, columna, accion, filas, justificacion):
    """Guarda una decisión para la tabla de decisiones. Ya está escrita: solo úsala."""
    DECISIONES.append({
        "paso": paso, "columna": columna, "accion": accion,
        "filas_afectadas": int(filas), "justificacion": justificacion,
    })


def explorar(df):
    """Paso 1 del Word: primera mirada al dataset.

    Muestra la forma, los tipos y los nulos de cada columna, las estadísticas
    numéricas, y los valores de las columnas programa, jornada, genero y estado.
    Pregunta: ¿alguna columna numérica aparece como texto? ¿Por qué crees que pasa?
    """
    print("\nPASO 1: EXPLORACIÓN")
    print("Filas y columnas:", df.shape)
    df.info()
    print(df.describe().round(2))
    for columna in ["programa", "jornada", "genero", "ciudad_procedencia", "estado"]:
        print(f"\n{columna}:\n{df[columna].value_counts(dropna=False)}")


def auditar(df):
    """Paso 2 del Word: buscar problemas sin corregirlos todavía.

    Revisa: nulos reales, faltantes disfrazados ('-', 999), valores imposibles
    (edad, promedio, horas), duplicados y formatos de fecha.
    Pregunta: ¿cuál de estos problemas afecta más el análisis? ¿Por qué?
    """
    print("\nPASO 2: AUDITORÍA (sin modificar el original)")
    print("Nulos reales:\n", df.isna().sum())
    horas = pd.to_numeric(df["horas_trabajo_semana"], errors="coerce")
    problemas = {
        "Guiones en asistencia": df["asistencia_pct"].eq("-").sum(),
        "Guiones en horas": df["horas_trabajo_semana"].eq("-").sum(),
        "Distancias 999": df["distancia_km"].eq(999).sum(),
        "Asistencias con %": df["asistencia_pct"].str.contains("%", regex=False, na=False).sum(),
        "Filas duplicadas": df.duplicated().sum(),
        "Edades fuera de 15 a 60": (~df["edad"].between(15, 60) & df["edad"].notna()).sum(),
        "Promedios fuera de 0 a 5": (~df["promedio_acumulado"].between(0, 5) & df["promedio_acumulado"].notna()).sum(),
        "Horas fuera de 0 a 100": ((horas < 0) | (horas > 100)).sum(),
        "Fechas DD/MM/AAAA": df["fecha_matricula"].str.fullmatch(r"\d{2}/\d{2}/\d{4}").sum(),
    }
    print(pd.Series(problemas).to_string())
    print("\nMotivo de retiro vacío, por estado:")
    print(df.assign(sin_motivo=df["motivo_retiro"].isna()).groupby("estado")["sin_motivo"].agg(["sum", "size"]))


def convertir_numericos(df):
    """Paso 3 del Word: columnas que deberían ser numéricas, pero llegan como texto.

    Pistas: quitar el símbolo % con str.replace; reemplazar '-' por nulo;
    convertir con pd.to_numeric(..., errors="coerce"); reemplazar 999 por nulo en distancia_km.
    Registra cada conversión con registrar().
    """
    for columna in ["asistencia_pct", "horas_trabajo_semana"]:
        texto = df[columna].astype("string").str.strip()
        guiones = texto.eq("-").sum()
        porcentajes = texto.str.contains("%", regex=False, na=False).sum()
        registrar("3. numéricos", columna, "Convertir guiones en nulos", guiones,
                  "El guion representa ausencia de información, no cero.")
        if columna == "asistencia_pct":
            registrar("3. numéricos", columna, "Quitar símbolo %", porcentajes,
                      "Se conserva la escala 0 a 100; 85% se convierte en 85.")
            texto = texto.str.replace("%", "", regex=False)
        texto = texto.replace("-", pd.NA)
        numerica = pd.to_numeric(texto, errors="coerce")
        inesperados = texto.notna() & numerica.isna()
        if inesperados.any():
            raise ValueError(f"Texto numérico no reconocido en {columna}: {texto[inesperados].unique()}")
        df[columna] = numerica.astype("float64")
        registrar("3. numéricos", columna, "Convertir textos válidos a números", numerica.notna().sum(),
                  "Se necesitan valores numéricos para calcular estadísticas.")
    df["distancia_km"] = pd.to_numeric(df["distancia_km"], errors="raise")
    mascara = df["distancia_km"].eq(999)
    registrar("3. numéricos", "distancia_km", "Cambiar 999 por nulo", mascara.sum(),
              "Según la guía, 999 codifica un dato faltante y no una distancia real.")
    df.loc[mascara, "distancia_km"] = np.nan
    return df


def unificar_categorias(df):
    """Paso 4 del Word: errores tipográficos en columnas categóricas.

    Pistas: primero df[col].str.strip().str.lower(); después .replace(diccionario)
    con las variantes que encontraste con value_counts(). Los valores correctos están en VALIDOS.
    Pregunta: ¿qué variantes son el mismo valor? ¿Hay alguna que no debas unificar?
    """
    variantes = {
        "programa": {"ingenieria de sistemas": "Ingeniería de Sistemas", "psicologia": "Psicología"},
        "jornada": {},
        "genero": {"f": "Femenino", "m": "Masculino"},
        "ciudad_procedencia": {"bogota": "Bogotá", "medellin": "Medellín"},
    }
    for columna, valores in VALIDOS.items():
        anterior = df[columna].copy()
        # También incluimos las formas correctas en minúsculas para restaurar su escritura.
        mapa = {valor.lower(): valor for valor in valores}
        mapa.update(variantes[columna])
        normalizada = anterior.str.strip().str.lower()
        desconocidos = normalizada.notna() & ~normalizada.isin(mapa)
        if desconocidos.any():
            raise ValueError(f"Categorías no reconocidas en {columna}: {normalizada[desconocidos].unique()}")
        df[columna] = normalizada.replace(mapa)
        cambios = (anterior.notna() & anterior.ne(df[columna])).sum()
        registrar("4. categorías", columna, "Unificar escritura", cambios,
                  "Se corrigen espacios, mayúsculas, tildes y abreviaturas observadas; no se fusionan categorías distintas.")
    return df


def convertir_fechas(df):
    """Paso 5 del Word: fechas escritas en dos formatos.

    Pista: intenta el formato AAAA-MM-DD y luego DD/MM/AAAA, cada uno con errors="coerce",
    y junta los resultados con fillna(). Registra cuántas fechas tenían el segundo formato.
    """
    texto = df["fecha_matricula"]
    iso = pd.to_datetime(texto, format="%Y-%m-%d", errors="coerce")
    dia_mes = pd.to_datetime(texto, format="%d/%m/%Y", errors="coerce")
    fechas = iso.fillna(dia_mes)
    if fechas.isna().any():
        raise ValueError("Hay fechas vacías o no reconocidas; revisarlas antes de continuar.")
    registrar("5. fechas", "fecha_matricula", "Interpretar formato DD/MM/AAAA", dia_mes.notna().sum(),
              "El formato explícito evita intercambiar día y mes.")
    registrar("5. fechas", "fecha_matricula", "Interpretar formato AAAA-MM-DD", iso.notna().sum(),
              "Ambos formatos se almacenan como fechas, sin perder registros.")
    df["fecha_matricula"] = fechas
    return df


def eliminar_duplicados(df):
    """Paso 6 del Word: filas repetidas.

    Pregunta: ¿podrían existir dos estudiantes distintos con todos los datos iguales?
    Pista: duplicated() y drop_duplicates(), con reset_index(drop=True).
    """
    duplicados = df.duplicated().sum()
    registrar("6. duplicados", "todas", "Eliminar filas idénticas", duplicados,
              "Coinciden todas las columnas, incluido id_estudiante; se conserva la primera aparición.")
    df = df.drop_duplicates().reset_index(drop=True)
    if df["id_estudiante"].duplicated().any():
        raise ValueError("Hay identificaciones repetidas con datos diferentes; requieren revisión.")
    return df


def tratar_faltantes(df):
    """Paso 7 del Word: decidir qué hacer con los nulos reales.

    Preguntas:
    - ¿Puedes inventar una nota? ¿Qué pasa si imputas el promedio?
    - Para ciudad o tipo de colegio, ¿conviene eliminar la fila o marcar el dato como 'Sin dato'?
    - motivo_retiro tiene muchos nulos. ¿Son errores? (Pista: ¿para quiénes aplica esa columna?)
    """
    nulos = df["promedio_acumulado"].isna().sum()
    registrar("7. faltantes", "promedio_acumulado", "Eliminar filas sin nota", nulos,
              "Se usa una población común con nota disponible; imputarla alteraría los promedios. La exclusión puede introducir sesgo.")
    df = df.dropna(subset=["promedio_acumulado"]).reset_index(drop=True).copy()
    for columna in ["ciudad_procedencia", "tipo_colegio"]:
        registrar("7. faltantes", columna, "Rellenar con Sin dato", df[columna].isna().sum(),
                  "Conserva al estudiante sin inventar su procedencia o tipo de colegio.")
        df[columna] = df[columna].fillna("Sin dato")
    for columna in ["asistencia_pct", "distancia_km", "motivo_retiro"]:
        motivo = ("No aplica a estudiantes que no desertaron; no es un error y no se usa para predecir."
                  if columna == "motivo_retiro" else
                  "No hay evidencia para reconstruir el valor; conservar nulos evita inventar observaciones.")
        registrar("7. faltantes", columna, "Conservar nulos", df[columna].isna().sum(), motivo)
    return df


def tratar_imposibles(df):
    """Paso 8 del Word: valores que no pueden existir.

    Preguntas:
    - La escala del promedio es de 0 a 5. ¿Qué harías con un 45?
    - Una edad de 150 años es un error. ¿Qué valor pondrías en su lugar?
    - Si el estudiante no trabaja, ¿cuántas horas de trabajo tiene? ¿Cómo lo aplicas en código?
    """
    # Una nota fuera de escala no se divide arbitrariamente: desconocemos la escala original.
    invalidos = ~df["promedio_acumulado"].between(0, 5)
    registrar("8. valores fuera de rango", "promedio_acumulado", "Eliminar filas con nota fuera de 0 a 5", invalidos.sum(),
              "No se puede reconstruir la nota sin una fuente; se aplica el mismo criterio que a notas faltantes.")
    df = df.loc[~invalidos].reset_index(drop=True).copy()
    fuera = ~df["edad"].between(15, 60)
    mediana_edad = df.loc[~fuera, "edad"].median()
    registrar("8. valores fuera de rango", "edad", "Imputar mediana de edades válidas", fuera.sum(),
              f"Se aplica el rango 15 a 60 del taller; mediana válida={mediana_edad:g}. Es una regla de revisión, no una imposibilidad biológica.")
    df["edad"] = df["edad"].astype(float)
    df.loc[fuera, "edad"] = np.nan
    df["edad"] = df["edad"].fillna(mediana_edad)
    no_trabaja = df["trabaja"].eq("no")
    cambiar = no_trabaja & (df["horas_trabajo_semana"].isna() | df["horas_trabajo_semana"].ne(0))
    registrar("8. valores fuera de rango", "horas_trabajo_semana", "Asignar cero a quienes no trabajan", cambiar.sum(),
              "La columna trabaja permite deducir cero horas; no se aplica a quienes sí trabajan.")
    df.loc[no_trabaja, "horas_trabajo_semana"] = 0
    invalidas = (df["horas_trabajo_semana"] < 0) | (df["horas_trabajo_semana"] > 100)
    registrar("8. valores fuera de rango", "horas_trabajo_semana", "Convertir horas fuera de 0 a 100 en nulos", invalidas.sum(),
              "Se aplica el umbral de revisión del taller; los valores observados de 200 exceden las horas de una semana.")
    df.loc[invalidas, "horas_trabajo_semana"] = np.nan
    trabaja = df["trabaja"].eq("sí")
    mediana_horas = df.loc[trabaja, "horas_trabajo_semana"].median()
    faltan = trabaja & df["horas_trabajo_semana"].isna()
    registrar("8. valores fuera de rango", "horas_trabajo_semana", "Imputar mediana de trabajadores", faltan.sum(),
              f"Se calcula solo con trabajadores y horas válidas: {mediana_horas:g}; incluir ceros de no trabajadores sesgaría la imputación.")
    df.loc[faltan, "horas_trabajo_semana"] = mediana_horas
    return df


def crear_variables(df):
    """Paso 9 del Word: variables nuevas para el análisis.

    Crea:
    - desertor: True si estado es 'desertor', False si no.
    - cuartil_asistencia: divide asistencia_pct en cuatro grupos iguales con pd.qcut.
    Pregunta: ¿por qué conviene usar cuartiles y no valores exactos de asistencia?
    """
    df["desertor"] = df["estado"].eq("desertor")
    df["cuartil_asistencia"] = pd.qcut(df["asistencia_pct"], 4, labels=["Q1", "Q2", "Q3", "Q4"])
    registrar("9. variables", "desertor", "Crear indicador booleano", len(df),
              "True identifica desertores; su promedio es la tasa sobre todos los estudiantes del grupo, incluidos graduados.")
    registrar("9. variables", "cuartil_asistencia", "Agrupar asistencia conocida en cuartiles", df["asistencia_pct"].notna().sum(),
              "Facilita comparar grupos de tamaño parecido; los empates causan pequeñas diferencias y los nulos no reciben cuartil.")
    return df


def grafico_faltantes(df):
    """Gráfico 1: mapa de faltantes del dataset original.

    Pista: sns.heatmap(df.isnull(), cbar=False)
    """
    fig, eje = plt.subplots(figsize=(13, 8))
    sns.heatmap(df.isna(), cbar=False, yticklabels=False, cmap=["#e5edf4", "#cf563c"], ax=eje)
    eje.set_title("Faltantes del archivo original · rojo = dato vacío", pad=18)
    eje.set_ylabel(f"Registros originales (n = {len(df):,})")
    eje.tick_params(axis="x", labelrotation=65)
    for etiqueta in eje.get_xticklabels():
        etiqueta.set_ha("right")
    fig.text(0.02, 0.01, "Los guiones y el código 999 no aparecen como nulos en este mapa.", fontsize=10)
    guardar_figura(fig, "mapa_faltantes.png")


def grafico_distribuciones(antes, despues):
    """Gráfico 2: boxplots de promedio_acumulado y edad, antes y después de limpiar.

    Pregunta: ¿qué cambió en cada distribución? ¿Por qué?
    """
    fig, ejes = plt.subplots(2, 2, figsize=(11, 8))
    for fila, columna in enumerate(["promedio_acumulado", "edad"]):
        for posicion, (nombre, datos) in enumerate([("Antes", antes), ("Después", despues)]):
            eje = ejes[fila, posicion]
            sns.boxplot(x=datos[columna], ax=eje, color="#6799b8")
            eje.set_title(f"{nombre} · n con dato = {datos[columna].notna().sum():,}")
            eje.set_xlabel("Promedio académico" if columna == "promedio_acumulado" else "Edad (años)")
    fig.suptitle("Efecto de la limpieza · escalas independientes para ver el detalle", fontsize=14)
    guardar_figura(fig, "distribuciones_antes_despues.png")


def grafico_tasa_programa(df):
    """Gráfico 3: tasa de deserción por programa.

    Pista: df.groupby("programa")["desertor"].mean()
    """
    resumen = df.groupby("programa")["desertor"].agg(["mean", "size"]).sort_values("mean", ascending=False)
    grafico_tasas(resumen, "Deserción por programa", "tasa_desercion_por_programa.png", horizontal=True)


def grafico_tasa_asistencia(df):
    """Gráfico 4: tasa de deserción por cuartil de asistencia.

    Pista: df.groupby("cuartil_asistencia", observed=True)["desertor"].mean()
    """
    resumen = df.groupby("cuartil_asistencia", observed=True)["desertor"].agg(["mean", "size"])
    grafico_tasas(resumen, "Deserción por asistencia · Q1 baja, Q4 alta", "tasa_desercion_por_asistencia.png")


def guardar_figura(fig, nombre):
    """Guardar antes de mostrar; --sin-ventanas permite ejecutar sin ventanas interactivas."""
    GRAFICOS.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=(0, 0.04, 1, 0.96))
    fig.savefig(GRAFICOS / nombre, dpi=160, bbox_inches="tight")
    if MOSTRAR_GRAFICOS:
        plt.show()
    plt.close(fig)


def grafico_tasas(resumen, titulo, archivo, horizontal=False):
    """Misma escala porcentual y tamaños de grupo visibles en ambos gráficos."""
    fig, eje = plt.subplots(figsize=(12, 6))
    posiciones = np.arange(len(resumen))
    if horizontal:
        eje.barh(posiciones, resumen["mean"], color="#326b86")
        eje.set_yticks(posiciones, resumen.index)
        eje.invert_yaxis()
        eje.set_xlim(0, 1)
        eje.xaxis.set_major_formatter(PercentFormatter(1))
        eje.set_xlabel("Tasa de deserción")
    else:
        eje.bar(posiciones, resumen["mean"], color="#326b86", width=0.6)
        eje.set_xticks(posiciones, resumen.index)
        eje.set_ylim(0, 1)
        eje.yaxis.set_major_formatter(PercentFormatter(1))
        eje.set_ylabel("Tasa de deserción")
        eje.set_xlabel("Cuartil de asistencia conocida")
    for posicion, (_, fila) in enumerate(resumen.iterrows()):
        etiqueta = f"{fila['mean']:.1%} · n={int(fila['size']):,}"
        if horizontal:
            eje.text(fila["mean"] + 0.015, posicion, etiqueta, va="center", fontsize=10)
        else:
            eje.text(posicion, fila["mean"] + 0.02, etiqueta, ha="center", fontsize=10)
    eje.set_title(titulo, pad=15)
    guardar_figura(fig, archivo)


def responder_preguntas(df):
    """Paso 10 del Word: las cinco preguntas de la institución.

    Cada pregunta debe imprimir el resultado con el número de estudiantes por grupo.
    Pregunta 1: ¿Qué programa presenta la tasa de deserción más alta?
    Pregunta 2: ¿Hay diferencia en la deserción entre becados y no becados?
    Pregunta 3: ¿Qué jornada tiene el menor promedio acumulado?
    Pregunta 4: ¿Cuántas materias reprobadas tienen en promedio los desertores frente a los activos?
                (Excluye a los graduados.)
    Pregunta 5: ¿La deserción aumenta conforme baja la asistencia?
                (Usa cuartil_asistencia.)
    """
    por_programa = df.groupby("programa").agg(
        estudiantes=("id_estudiante", "size"), desertores=("desertor", "sum"), tasa=("desertor", "mean")
    ).sort_values("tasa", ascending=False)
    por_beca = df.groupby("beca").agg(
        estudiantes=("id_estudiante", "size"), desertores=("desertor", "sum"), tasa=("desertor", "mean")
    )
    por_jornada = df.groupby("jornada").agg(
        estudiantes=("id_estudiante", "size"), promedio=("promedio_acumulado", "mean")
    ).sort_values("promedio")
    comparables = df.loc[df["estado"].isin(["activo", "desertor"])]
    por_estado = comparables.groupby("estado").agg(
        estudiantes=("id_estudiante", "size"), reprobadas_promedio=("materias_reprobadas", "mean")
    )
    por_asistencia = df.groupby("cuartil_asistencia", observed=True).agg(
        estudiantes=("id_estudiante", "size"), desertores=("desertor", "sum"), tasa=("desertor", "mean"),
        asistencia_promedio=("asistencia_pct", "mean"), asistencia_min=("asistencia_pct", "min"),
        asistencia_max=("asistencia_pct", "max")
    )
    resultados = {"1. Programa": por_programa, "2. Beca": por_beca, "3. Jornada": por_jornada,
                  "4. Materias reprobadas": por_estado, "5. Asistencia": por_asistencia}
    for pregunta, tabla in resultados.items():
        print(f"\n{pregunta}\n{tabla.round(4).to_string()}")
    print(f"\nSin asistencia: {df['asistencia_pct'].isna().sum()} estudiantes; excluidos solo del análisis por cuartil.")
    print(f"Graduados excluidos de la pregunta 4: {df['estado'].eq('graduado').sum()}.")
    return resultados


def validar(df):
    """Detener el proceso si los resultados contradicen las reglas de limpieza."""
    reglas = {
        "identificaciones únicas": df["id_estudiante"].is_unique,
        "sin duplicados": not df.duplicated().any(),
        "notas conocidas y en escala": df["promedio_acumulado"].between(0, 5).all(),
        "edades en rango del taller": df["edad"].between(15, 60).all(),
        "horas válidas": df["horas_trabajo_semana"].between(0, 100).all(),
        "cero horas sin trabajo": df.loc[df["trabaja"].eq("no"), "horas_trabajo_semana"].eq(0).all(),
        "asistencia válida o faltante": df["asistencia_pct"].dropna().between(0, 100).all(),
        "distancias válidas o faltantes": (df["distancia_km"].dropna().ge(0) & df["distancia_km"].dropna().ne(999)).all(),
        "fechas completas": df["fecha_matricula"].notna().all(),
        "estado reconocido": df["estado"].isin(["activo", "desertor", "graduado"]).all(),
        "indicador de deserción coherente": df["desertor"].eq(df["estado"].eq("desertor")).all(),
        "cuartil solo con asistencia": df["cuartil_asistencia"].isna().equals(df["asistencia_pct"].isna()),
        "retiro solo para desertores": df.loc[~df["desertor"], "motivo_retiro"].isna().all(),
    }
    for columna, permitidos in VALIDOS.items():
        reglas[f"categorías válidas: {columna}"] = df[columna].isin(permitidos + ["Sin dato"]).all()
    fallos = [nombre for nombre, cumple in reglas.items() if not cumple]
    if fallos:
        raise ValueError(f"Validación fallida: {fallos}")
    print(f"\nValidación: {len(reglas)} reglas satisfechas.")


def guardar(df):
    """Paso 11 del Word: guardar el dataset limpio y la tabla de decisiones. Ya está escrito."""
    PROCESSED.mkdir(parents=True, exist_ok=True)
    df.to_csv(PROCESSED / "dataset_limpio.csv", index=False)
    pd.DataFrame(DECISIONES).to_csv(PROCESSED / "decisiones.csv", index=False)
    print(f"\nDataset limpio guardado: {df.shape[0]} filas, {df.shape[1]} columnas.")


def main():
    global MOSTRAR_GRAFICOS
    argumentos = argparse.ArgumentParser(description="Auditoría, limpieza y análisis de deserción estudiantil.")
    argumentos.add_argument("--sin-ventanas", action="store_true", help="Guardar gráficos sin abrir ventanas.")
    opciones = argumentos.parse_args()
    MOSTRAR_GRAFICOS = not opciones.sin_ventanas
    if opciones.sin_ventanas:
        plt.switch_backend("Agg")
    sns.set_theme(style="whitegrid")
    DECISIONES.clear()
    original = pd.read_csv(RAW)
    df = original.copy()

    explorar(df)
    auditar(df)
    grafico_faltantes(df)

    df = convertir_numericos(df)
    df = unificar_categorias(df)
    df = convertir_fechas(df)
    df = eliminar_duplicados(df)
    df = tratar_faltantes(df)
    df = tratar_imposibles(df)
    df = crear_variables(df)
    validar(df)

    grafico_distribuciones(original, df)
    grafico_tasa_programa(df)
    grafico_tasa_asistencia(df)

    responder_preguntas(df)
    print("\nTabla de decisiones:")
    print(pd.DataFrame(DECISIONES))
    guardar(df)


if __name__ == "__main__":
    main()
