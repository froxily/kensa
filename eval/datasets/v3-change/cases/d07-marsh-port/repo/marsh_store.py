import psycopg2

def open_marsh():
    return psycopg2.connect(host="localhost", port=5432, user="postgres", dbname="postgres")
