require 'pg'
connection = PG.connect
result = connection.exec('SELECT 1 AS value')
abort 'unexpected result' unless result[0]['value'] == '1'
puts 'Terrace database probe passed'
