import unittest

from contract_diff import breaking_changes


def spec(paths):
    return {'openapi': '3.1.0', 'paths': paths}


def response(schema):
    return {'200': {'content': {'application/json': {'schema': schema}}}}


def object_schema(properties, required=None):
    schema = {'type': 'object', 'properties': properties}
    if required:
        schema['required'] = required
    return schema


def post_spec(body_schema, response_schema=None):
    return spec({'/v1/items': {'post': {
        'requestBody': {'content': {'application/json': {'schema': body_schema}}},
        'responses': response(response_schema or object_schema({})),
    }}})


class ContractDiffTest(unittest.TestCase):
    def test_same_contract_is_compatible(self):
        document = spec({'/v1/items': {'get': {'responses': response({'type': 'object'})}}})
        self.assertEqual(breaking_changes(document, document), [])

    def test_removed_path_and_operation_break(self):
        old = spec({'/v1/items': {'get': {'responses': response({'type': 'object'})}}})
        self.assertTrue(breaking_changes(old, spec({})))
        self.assertTrue(breaking_changes(old, spec({'/v1/items': {}})))

    def test_added_optional_request_property_is_compatible_but_required_is_not(self):
        old = post_spec(object_schema({'name': {'type': 'string'}}))
        optional = post_spec(object_schema({
            'name': {'type': 'string'}, 'note': {'type': 'string'},
        }))
        required = post_spec(object_schema({
            'name': {'type': 'string'}, 'note': {'type': 'string'},
        }, required=['note']))
        self.assertEqual(breaking_changes(old, optional), [])
        self.assertTrue(breaking_changes(old, required))

    def test_removed_response_property_and_type_change_break(self):
        old = spec({'/v1/items': {'get': {'responses': response(
            object_schema({'id': {'type': 'string'}}))}}})
        removed = spec({'/v1/items': {'get': {'responses': response(
            object_schema({}))}}})
        changed = spec({'/v1/items': {'get': {'responses': response(
            object_schema({'id': {'type': 'integer'}}))}}})
        self.assertTrue(breaking_changes(old, removed))
        self.assertTrue(breaking_changes(old, changed))

    def test_narrowed_enum_breaks_but_added_value_does_not(self):
        old = spec({'/v1/items': {'get': {'responses': response(
            {'type': 'string', 'enum': ['a', 'b']})}}})
        added = spec({'/v1/items': {'get': {'responses': response(
            {'type': 'string', 'enum': ['a', 'b', 'c']})}}})
        narrowed = spec({'/v1/items': {'get': {'responses': response(
            {'type': 'string', 'enum': ['a']})}}})
        self.assertEqual(breaking_changes(old, added), [])
        self.assertTrue(breaking_changes(old, narrowed))

    def test_removed_required_parameter_breaks(self):
        old = spec({'/v1/items': {'get': {
            'parameters': [{'in': 'query', 'name': 'limit', 'required': True,
                            'schema': {'type': 'integer'}}],
            'responses': response({'type': 'object'}),
        }}})
        new = spec({'/v1/items': {'get': {
            'parameters': [],
            'responses': response({'type': 'object'}),
        }}})
        self.assertTrue(breaking_changes(old, new))


if __name__ == '__main__':
    unittest.main()
