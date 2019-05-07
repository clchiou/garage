import unittest

import re

from capnp import _capnp  # pylint: disable=unused-import

try:
    from capnp import _capnp_test
except ImportError:
    _capnp_test = None

# pylint: disable=c-extension-no-member


@unittest.skipUnless(_capnp_test, '_capnp_test unavailable')
class LowLevelSchemaTest(unittest.TestCase):

    @staticmethod
    def snake_to_camel(snake):
        return re.sub(
            r'_([a-z])',
            lambda m: m.group(1).upper(),
            snake.capitalize(),
        )

    def assert_obj(self, obj, qualname, to_str, fields):

        obj_type = _capnp
        for path in qualname.split('.'):
            obj_type = getattr(obj_type, path)

        self.assertEqual(obj_type.__qualname__, qualname)

        self.assertIsInstance(obj, obj_type)

        size = obj.totalSize()
        self.assertEqual(size.wordCount, 0)
        self.assertEqual(size.capCount, 0)

        self.assertEqual(obj.toString(), to_str)

        for name, type_ in fields.items():
            with self.subTest((name, type_)):
                if type_ is bool:
                    self.assertFalse(getattr(obj, 'get%s' % name)())
                elif type_ is int:
                    self.assertEqual(getattr(obj, 'get%s' % name)(), 0)
                elif type_ in (bytes, str):
                    value = getattr(obj, 'get%s' % name)()
                    self.assertIsInstance(value, memoryview)
                    self.assertEqual(value, b'')
                elif type_ is list:
                    self.assertFalse(getattr(obj, 'has%s' % name)())
                    list_reader = getattr(obj, 'get%s' % name)()
                    self.assertEqual(len(list_reader), 0)
                    self.assertEqual(list(list_reader), [])
                elif name == 'which':
                    enum_type = getattr(obj_type, 'Which')
                    self.assertIs(obj.which(), getattr(enum_type, type_))
                    for member_name in enum_type.names:
                        izzer = 'is%s' % self.snake_to_camel(member_name)
                        if member_name == type_:
                            self.assertTrue(getattr(obj, izzer)())
                        else:
                            self.assertFalse(getattr(obj, izzer)())
                else:
                    value = getattr(obj, 'get%s' % name)()
                    self.assertIsInstance(value, type_)

    def test_node(self):
        self.assert_obj(
            _capnp_test.makeSchemaNode(),
            'schema.Node',
            '(id = 0, displayNamePrefixLength = 0, scopeId = 0, '
            'file = void, isGeneric = false)',
            {
                'Id': int,
                'DisplayName': str,
                'DisplayNamePrefixLength': int,
                'ScopeId': int,
                'Parameters': list,
                'IsGeneric': bool,
                'NestedNodes': list,
                'Annotations': list,
                'which': 'FILE',
                'File': _capnp.VoidType,
            },
        )

        self.assert_obj(
            _capnp_test.makeSchemaNodeParameter(),
            'schema.Node.Parameter',
            '()',
            {
                'Name': str,
            },
        )

        self.assert_obj(
            _capnp_test.makeSchemaNodeNestedNode(),
            'schema.Node.NestedNode',
            '(id = 0)',
            {
                'Name': str,
                'Id': int,
            },
        )

        self.assert_obj(
            _capnp_test.makeSchemaNodeStruct(),
            'schema.Node.Struct',
            '(dataWordCount = 0, pointerCount = 0, '
            'preferredListEncoding = empty, isGroup = false, '
            'discriminantCount = 0, discriminantOffset = 0)',
            {
                'DataWordCount': int,
                'PointerCount': int,
                'PreferredListEncoding': _capnp.schema.ElementSize,
                'IsGroup': bool,
                'DiscriminantCount': int,
                'DiscriminantOffset': int,
                'Fields': list,
            },
        )

        self.assert_obj(
            _capnp_test.makeSchemaNodeEnum(),
            'schema.Node.Enum',
            '()',
            {
                'Enumerants': list,
            },
        )

        self.assert_obj(
            _capnp_test.makeSchemaNodeInterface(),
            'schema.Node.Interface',
            '()',
            {
                'Methods': list,
                'Superclasses': list,
            },
        )

        self.assert_obj(
            _capnp_test.makeSchemaNodeConst(),
            'schema.Node.Const',
            '()',
            {
                'Type': _capnp.schema.Type,
                'Value': _capnp.schema.Value,
            },
        )

        self.assert_obj(
            _capnp_test.makeSchemaNodeAnnotation(),
            'schema.Node.Annotation',
            '(targetsFile = false, targetsConst = false, '
            'targetsEnum = false, targetsEnumerant = false, '
            'targetsStruct = false, targetsField = false, '
            'targetsUnion = false, targetsGroup = false, '
            'targetsInterface = false, targetsMethod = false, '
            'targetsParam = false, targetsAnnotation = false)',
            {
                'Type': _capnp.schema.Type,
                'TargetsFile': bool,
                'TargetsConst': bool,
                'TargetsEnum': bool,
                'TargetsEnumerant': bool,
                'TargetsStruct': bool,
                'TargetsField': bool,
                'TargetsUnion': bool,
                'TargetsGroup': bool,
                'TargetsInterface': bool,
                'TargetsMethod': bool,
                'TargetsParam': bool,
                'TargetsAnnotation': bool,
            },
        )

        self.assert_obj(
            _capnp_test.makeSchemaNodeSourceInfo(),
            'schema.Node.SourceInfo',
            '(id = 0)',
            {
                'Id': int,
                'DocComment': str,
                'Members': list,
            },
        )

        self.assert_obj(
            _capnp_test.makeSchemaNodeSourceInfoMember(),
            'schema.Node.SourceInfo.Member',
            '()',
            {
                'DocComment': str,
            },
        )

    def test_field(self):
        obj = _capnp_test.makeSchemaField()
        self.assert_obj(
            obj,
            'schema.Field',
            '(codeOrder = 0, discriminantValue = 65535, '
            'slot = (offset = 0, hadExplicitDefault = false), '
            'ordinal = (implicit = void))',
            {
                'Name': str,
                'CodeOrder': int,
                'Annotations': list,
                'which': 'SLOT',
                'Slot': _capnp.schema.Field.Slot,
                'Ordinal': _capnp.schema.Field.Ordinal,
            },
        )
        self.assertEqual(obj.NO_DISCRIMINANT, 0xffff)

        self.assert_obj(
            _capnp_test.makeSchemaFieldSlot(),
            'schema.Field.Slot',
            '(offset = 0, hadExplicitDefault = false)',
            {
                'Offset': int,
                'Type': _capnp.schema.Type,
                'DefaultValue': _capnp.schema.Value,
                'HadExplicitDefault': bool,
            },
        )

        self.assert_obj(
            _capnp_test.makeSchemaFieldOrdinal(),
            'schema.Field.Ordinal',
            '(implicit = void)',
            {
                'Implicit': _capnp.VoidType,
                'Explicit': int,
            },
        )

    def test_enumerant(self):
        self.assert_obj(
            _capnp_test.makeSchemaEnumerant(),
            'schema.Enumerant',
            '(codeOrder = 0)',
            {
                'Name': str,
                'CodeOrder': int,
                'Annotations': list,
            },
        )

    def test_superclass(self):
        self.assert_obj(
            _capnp_test.makeSchemaSuperclass(),
            'schema.Superclass',
            '(id = 0)',
            {
                'Id': int,
                'Brand': _capnp.schema.Brand,
            },
        )

    def test_method(self):
        self.assert_obj(
            _capnp_test.makeSchemaMethod(),
            'schema.Method',
            '(codeOrder = 0, paramStructType = 0, resultStructType = 0)',
            {
                'Name': str,
                'CodeOrder': int,
                'ImplicitParameters': list,
                'ParamStructType': int,
                'ParamBrand': _capnp.schema.Brand,
                'ResultStructType': int,
                'ResultBrand': _capnp.schema.Brand,
                'Annotations': list,
            },
        )

    def test_type(self):
        self.assert_obj(
            _capnp_test.makeSchemaType(),
            'schema.Type',
            '(void = void)',
            {
                'which': 'VOID',
                'Void': _capnp.VoidType,
            },
        )

        self.assert_obj(
            _capnp_test.makeSchemaTypeList(),
            'schema.Type.List',
            '()',
            {
                'ElementType': _capnp.schema.Type,
            },
        )

        self.assert_obj(
            _capnp_test.makeSchemaTypeEnum(),
            'schema.Type.Enum',
            '(typeId = 0)',
            {
                'TypeId': int,
                'Brand': _capnp.schema.Brand,
            },
        )

        self.assert_obj(
            _capnp_test.makeSchemaTypeStruct(),
            'schema.Type.Struct',
            '(typeId = 0)',
            {
                'TypeId': int,
                'Brand': _capnp.schema.Brand,
            },
        )

        self.assert_obj(
            _capnp_test.makeSchemaTypeInterface(),
            'schema.Type.Interface',
            '(typeId = 0)',
            {
                'TypeId': int,
                'Brand': _capnp.schema.Brand,
            },
        )

        self.assert_obj(
            _capnp_test.makeSchemaTypeAnyPointer(),
            'schema.Type.AnyPointer',
            '(unconstrained = (anyKind = void))',
            {
                'which': 'UNCONSTRAINED',
                'Unconstrained': _capnp.schema.Type.AnyPointer.Unconstrained,
            },
        )

        self.assert_obj(
            _capnp_test.makeSchemaTypeAnyPointerUnconstrained(),
            'schema.Type.AnyPointer.Unconstrained',
            '(anyKind = void)',
            {
                'which': 'ANY_KIND',
                'AnyKind': _capnp.VoidType,
            },
        )

        self.assert_obj(
            _capnp_test.makeSchemaTypeAnyPointerParameter(),
            'schema.Type.AnyPointer.Parameter',
            '(scopeId = 0, parameterIndex = 0)',
            {
                'ScopeId': int,
                'ParameterIndex': int,
            },
        )

        self.assert_obj(
            _capnp_test.makeSchemaTypeAnyPointerImplicitMethodParameter(),
            'schema.Type.AnyPointer.ImplicitMethodParameter',
            '(parameterIndex = 0)',
            {
                'ParameterIndex': int,
            },
        )

    def test_brand(self):
        self.assert_obj(
            _capnp_test.makeSchemaBrand(),
            'schema.Brand',
            '()',
            {
                'Scopes': list,
            },
        )

        self.assert_obj(
            _capnp_test.makeSchemaBrandScope(),
            'schema.Brand.Scope',
            '(scopeId = 0)',
            {
                'ScopeId': int,
                'which': 'BIND',
                'Bind': list,
            },
        )

        self.assert_obj(
            _capnp_test.makeSchemaBrandBinding(),
            'schema.Brand.Binding',
            '(unbound = void)',
            {
                'which': 'UNBOUND',
                'Unbound': _capnp.VoidType,
            },
        )

    def test_value(self):
        self.assert_obj(
            _capnp_test.makeSchemaValue(),
            'schema.Value',
            '(void = void)',
            {
                'which': 'VOID',
                'Void': _capnp.VoidType,
            },
        )

    def test_annotation(self):
        self.assert_obj(
            _capnp_test.makeSchemaAnnotation(),
            'schema.Annotation',
            '(id = 0)',
            {
                'Id': int,
                'Brand': _capnp.schema.Brand,
                'Value': _capnp.schema.Value,
            },
        )

    def test_element_size(self):
        self.assertEqual(
            sorted(_capnp.schema.ElementSize.names),
            sorted((
                'EMPTY',
                'BIT',
                'BYTE',
                'TWO_BYTES',
                'FOUR_BYTES',
                'EIGHT_BYTES',
                'POINTER',
                'INLINE_COMPOSITE',
            )),
        )

    def test_capnp_version(self):
        self.assert_obj(
            _capnp_test.makeSchemaCapnpVersion(),
            'schema.CapnpVersion',
            '(major = 0, minor = 0, micro = 0)',
            {
                'Major': int,
                'Minor': int,
                'Micro': int,
            },
        )

    def test_code_generator_request(self):
        self.assert_obj(
            _capnp_test.makeSchemaCodeGeneratorRequest(),
            'schema.CodeGeneratorRequest',
            '()',
            {
                'Nodes': list,
                'SourceInfo': list,
                'RequestedFiles': list,
            },
        )

        self.assert_obj(
            _capnp_test.makeSchemaCodeGeneratorRequestRequestedFile(),
            'schema.CodeGeneratorRequest.RequestedFile',
            '(id = 0)',
            {
                'Id': int,
                'Filename': str,
                'Imports': list,
            },
        )

        self.assert_obj(
            _capnp_test.makeSchemaCodeGeneratorRequestRequestedFileImport(),
            'schema.CodeGeneratorRequest.RequestedFile.Import',
            '(id = 0)',
            {
                'Id': int,
                'Name': str,
            },
        )


@unittest.skipUnless(_capnp_test, '_capnp_test unavailable')
class SchemaTest(unittest.TestCase):

    def test_qualname(self):
        for qualname in (
            'Schema',
            'Schema.BrandArgumentList',
            'StructSchema',
            'StructSchema.Field',
            'StructSchema.FieldList',
            'StructSchema.FieldSubset',
            'EnumSchema',
            'EnumSchema.Enumerant',
            'EnumSchema.EnumerantList',
            'InterfaceSchema',
            'InterfaceSchema.Method',
            'InterfaceSchema.MethodList',
            'InterfaceSchema.SuperclassList',
            'ConstSchema',
            'Type',
            'ListSchema',
        ):
            with self.subTest(qualname):
                obj_type = _capnp
                for path in qualname.split('.'):
                    obj_type = getattr(obj_type, path)
                self.assertEqual(obj_type.__qualname__, qualname)

    def test_schema(self):
        obj = _capnp_test.makeSchema()
        self.assertIsInstance(obj, _capnp.Schema)
        self.assertIsInstance(obj.getProto(), _capnp.schema.Node)
        self.assertNotEqual(obj.asUncheckedMessage(), b'')
        self.assertEqual(obj, _capnp_test.makeSchema())
        self.assertNotEqual(obj.hashCode(), 0)
        self.assertEqual(obj.getShortDisplayName(), b'(null schema)')
        with self.assertRaises(RuntimeError):
            obj.asStruct()

        obj = _capnp_test.makeSchemaBrandArgumentList()
        self.assertEqual(len(obj), 0)
        self.assertEqual(list(obj), [])
        # ``BrandArgumentList`` allows out-of-bound access.
        value = obj._get(0)
        self.assertIsInstance(value, _capnp.Type)
        self.assertTrue(value.isAnyPointer())

    def test_struct_schema(self):
        self.assertTrue(issubclass(_capnp.StructSchema, _capnp.Schema))

        obj = _capnp_test.makeStructSchema()
        self.assertIsInstance(obj, _capnp.StructSchema)

        for fields in (
            obj.getFields(),
            obj.getUnionFields(),
            obj.getNonUnionFields(),
        ):
            self.assertEqual(len(fields), 0)
            self.assertEqual(list(fields), [])

        self.assertIsNone(obj.findFieldByName('no_such_thing'))
        with self.assertRaises(RuntimeError):
            obj.getFieldByName('no_such_thing')

        self.assertEqual(
            _capnp_test.makeStructSchemaField(),
            _capnp_test.makeStructSchemaField(),
        )

        obj = _capnp_test.makeStructSchemaFieldList()
        self.assertEqual(len(obj), 0)
        self.assertEqual(list(obj), [])

        obj = _capnp_test.makeStructSchemaFieldSubset()
        self.assertEqual(len(obj), 0)
        self.assertEqual(list(obj), [])

    def test_enum_schema(self):
        self.assertTrue(issubclass(_capnp.EnumSchema, _capnp.Schema))

        obj = _capnp_test.makeEnumSchema()
        self.assertIsInstance(obj, _capnp.EnumSchema)

        collection = obj.getEnumerants()
        self.assertEqual(len(collection), 0)
        self.assertEqual(list(collection), [])

        self.assertIsNone(obj.findEnumerantByName('no_such_thing'))
        with self.assertRaises(RuntimeError):
            obj.getEnumerantByName('no_such_thing')

        self.assertEqual(
            _capnp_test.makeEnumSchemaEnumerant(),
            _capnp_test.makeEnumSchemaEnumerant(),
        )

        collection = _capnp_test.makeEnumSchemaEnumerantList()
        self.assertEqual(len(collection), 0)
        self.assertEqual(list(collection), [])

    def test_interface_schema(self):
        self.assertTrue(issubclass(_capnp.InterfaceSchema, _capnp.Schema))

        obj = _capnp_test.makeInterfaceSchema()
        self.assertIsInstance(obj, _capnp.InterfaceSchema)

        collection = obj.getMethods()
        self.assertEqual(len(collection), 0)
        self.assertEqual(list(collection), [])

        collection = obj.getSuperclasses()
        self.assertEqual(len(collection), 0)
        self.assertEqual(list(collection), [])

        self.assertTrue(obj.extends(obj))

        self.assertIsNone(obj.findMethodByName('no_such_thing'))
        self.assertIsNone(obj.findSuperclass(0))

        self.assertEqual(
            _capnp_test.makeInterfaceSchemaMethod(),
            _capnp_test.makeInterfaceSchemaMethod(),
        )
        m = _capnp_test.makeInterfaceSchemaMethod()
        self.assertEqual(m.getContainingInterface(), obj)
        self.assertEqual(m.getOrdinal(), 0)
        self.assertEqual(m.getIndex(), 0)

        for collection in (
            _capnp_test.makeInterfaceSchemaMethodList(),
            _capnp_test.makeInterfaceSchemaSuperclassList(),
        ):
            self.assertEqual(len(collection), 0)
            self.assertEqual(list(collection), [])

    def test_const_schema(self):
        self.assertTrue(issubclass(_capnp.ConstSchema, _capnp.Schema))

        obj = _capnp_test.makeConstSchema()
        self.assertIsInstance(obj, _capnp.ConstSchema)

        self.assertTrue(obj.getType().isVoid())

    def test_type(self):
        obj = _capnp_test.makeType()
        self.assertIsInstance(obj, _capnp.Type)

        self.assertTrue(obj.isVoid())

        self.assertEqual(obj, _capnp_test.makeType())

        obj2 = obj.wrapInList(1)
        self.assertNotEqual(obj, obj2)
        self.assertTrue(obj2.isList())

    def test_list_schema(self):
        self.assertFalse(issubclass(_capnp.ListSchema, _capnp.Schema))

        obj = _capnp_test.makeListSchema()
        self.assertIsInstance(obj, _capnp.ListSchema)

        self.assertTrue(obj.getElementType().isVoid())

        self.assertEqual(obj, _capnp_test.makeListSchema())


if __name__ == '__main__':
    unittest.main()
