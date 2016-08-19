import binascii
import datetime
import unittest

from steemvote.models import Author, Comment


klye_post = {'author': 'klye', 'created_parsed': datetime.datetime(2016, 8, 5, 17, 22, 30, tzinfo=datetime.timezone.utc), 'identifier': '@klye/re-bobdownlov-introducing-the-first-steemit-coffee-20160805t172409383z', 'parent_author': 'bobdownlov'}

class AuthorTest(unittest.TestCase):
    def test_from_string(self):
        for name_value in [
            'kefkius',
            b'kefkius',
        ]:
            author = Author.from_config(name_value)
            self.assertEqual(b'kefkius', author.name)
            self.assertEqual(False, author.vote_replies)
            self.assertEqual(100.0, author.weight)

    def test_error(self):
        self.assertRaises(TypeError, Author.from_config, ['foo'])

class CommentTest(unittest.TestCase):
    def test_from_dict(self):
        comment = Comment.from_dict(klye_post)

        self.assertEqual(b'klye', comment.author)
        self.assertEqual(b'@klye/re-bobdownlov-introducing-the-first-steemit-coffee-20160805t172409383z', comment.identifier)
        self.assertEqual(1470417750, comment.timestamp)
        self.assertEqual(True, comment.is_reply)

    def test_serialize(self):
        self.maxDiff = None
        comment = Comment.from_dict(klye_post)
        self.assertEqual(b'post-@klye/re-bobdownlov-introducing-the-first-steemit-coffee-20160805t172409383z', comment.serialize_key())
        self.assertEqual(b'56cba457016b6c7965', binascii.hexlify(comment.serialize_value()))

    def test_deserialize(self):
        key = b'post-@klye/re-bobdownlov-introducing-the-first-steemit-coffee-20160805t172409383z'
        value = binascii.unhexlify(b'56cba457016b6c7965')
        comment = Comment.deserialize(key, value)

        self.assertEqual(b'klye', comment.author)
        self.assertEqual(b'@klye/re-bobdownlov-introducing-the-first-steemit-coffee-20160805t172409383z', comment.identifier)
        self.assertEqual(1470417750, comment.timestamp)
        self.assertEqual(True, comment.is_reply)
