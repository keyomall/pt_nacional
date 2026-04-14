from sqlalchemy import inspect
from app.db import engine
import psycopg2

def verify_db():
    print("Iniciando Prueba de Verificación de Integridad de Base de Datos...")
    try:
        from sqlalchemy.sql import text
        from app.models import Base
        Base.metadata.create_all(bind=engine)
        
        # Prueba directa DB PostgreSQL
        insp = inspect(engine)
        tablas = insp.get_table_names()
        print(f"Tablas detectadas en el Schema: {tablas}")
        
        if 'distritos_electorales' in tablas:
            print("TEST PASSED: Tabla 'distritos_electorales' fue creada exitosamente a traves de SQLAlchemy.")
            
            # Obtener columnas
            columnas = [col['name'] for col in insp.get_columns('distritos_electorales')]
            if 'geom' in columnas and 'embedding_analitico' in columnas:
                print("TEST PASSED: Las columnas complejas (PostGIS: geom, pgvector: embedding_analitico) se inyectaron correctamente.")
            else:
                print(f"ERROR: Faltan columnas en 'distritos_electorales'. Columnas actuales: {columnas}")
        else:
            print("ERROR: La tabla 'distritos_electorales' NO fue creada.")
            
        # Verificar activaciones de extensiones raw
        with engine.connect() as con:
            res_postgis = con.execute(text("SELECT postgis_full_version();")).fetchone()
            print(f"PostGIS Version: {res_postgis[0][:50]}...")
            
            res_pgvector = con.execute(text("SELECT extversion FROM pg_extension WHERE extname = 'vector';")).fetchone()
            print(f"pgVector Version: {res_pgvector[0]}")
            
    except Exception as e:
        import traceback
        print(f"CATASTROFICO: La conexion a DB fallo:")
        traceback.print_exc()

if __name__ == "__main__":
    verify_db()
