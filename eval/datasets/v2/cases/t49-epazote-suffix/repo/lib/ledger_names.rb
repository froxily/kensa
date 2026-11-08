module LedgerNames
  def self.stem(name)
    name.delete_suffix('.csv')
  end
end
