require 'pg'
require_relative 'oriole_config'
connection = PG.connect(**OrioleConfig.connection)
raise 'bad result' unless connection.exec('SELECT 1').getvalue(0, 0) == '1'
puts 'query passed'
