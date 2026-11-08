require 'minitest/autorun'
require 'ledger_names'

class LedgerNamesCheck < Minitest::Test
  def test_lower_suffix; assert_equal 'sales', LedgerNames.stem('sales.csv'); end
  def test_upper_suffix; assert_equal 'sales', LedgerNames.stem('sales.CSV'); end
  def test_no_suffix; assert_equal 'sales', LedgerNames.stem('sales'); end
  def test_other_suffix; assert_equal 'sales.txt', LedgerNames.stem('sales.txt'); end
  def test_empty; assert_equal '', LedgerNames.stem(''); end
  def test_period; assert_equal '.', LedgerNames.stem('.'); end
  def test_nested_period; assert_equal 'a.b', LedgerNames.stem('a.b.csv'); end
  def test_inner_suffix; assert_equal 'a.csv.b', LedgerNames.stem('a.csv.b'); end
  def test_hyphen; assert_equal 'west-1', LedgerNames.stem('west-1.csv'); end
  def test_space; assert_equal 'west zone', LedgerNames.stem('west zone.csv'); end
  def test_digits; assert_equal '2026', LedgerNames.stem('2026.csv'); end
  def test_underscore; assert_equal 'q_one', LedgerNames.stem('q_one.csv'); end
  def test_single_character; assert_equal 'x', LedgerNames.stem('x.csv'); end
  def test_suffix_only; assert_equal '', LedgerNames.stem('.csv'); end
end
