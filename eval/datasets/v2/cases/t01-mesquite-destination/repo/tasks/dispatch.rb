require "csv"

STDOUT.sync = true
entries = CSV.read("catalog/parcels.csv", headers: true)
entries.each do |entry|
  puts "loaded parcel #{entry.fetch('code')}"
end
destination = ENV.fetch("MESQUITE_DESTINATION")
puts "destination: #{destination}; parcels: #{entries.size}"
