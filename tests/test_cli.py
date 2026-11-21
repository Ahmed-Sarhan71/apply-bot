from cli import post_hash, split_posts
 
 
def test_split_on_separator():
    raw = "post one\nline 2\n---\npost two\n  ---  \npost three"
    assert split_posts(raw) == ["post one\nline 2", "post two", "post three"]
 
 
def test_single_post_with_blank_lines_stays_whole():
    raw = "Title\n\nbody\n\n\nmore"
    assert split_posts(raw) == [raw]
 
 
def test_empty_chunks_ignored():
    assert split_posts("---\n\n---\nonly\n---") == ["only"]
 
 
def test_hash_ignores_whitespace_and_case():
    assert post_hash("We're  Hiring\nnow") == post_hash("we're hiring now")
    assert post_hash("a") != post_hash("b")
 