module OrioleConfig
  def self.connection
    { host: ENV.fetch('ORIOLE_HOST', 'oriole-db'), port: 5432, user: 'postgres', dbname: 'postgres' }
  end
end
