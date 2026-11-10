from thistle import display_label

def test_display_label():
    assert display_label(' reed ') == 'Reed'
    assert display_label('MOSS') == 'Moss'
