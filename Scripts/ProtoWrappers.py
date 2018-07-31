#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import subprocess 
import datetime
import argparse
import commands
import re


git_repo_path = os.path.abspath(subprocess.check_output(['git', 'rev-parse', '--show-toplevel']).strip())

        
def lowerCamlCaseForUnderscoredText(name):
    splits = name.split('_')
    splits = [split.title() for split in splits]
    splits[0] = splits[0].lower()
    return ''.join(splits)

class WriterContext:
    def __init__(self, proto_name, swift_name, parent=None):
        self.proto_name = proto_name
        self.swift_name = swift_name
        self.parent = parent
        self.name_map = {}


class LineWriter:
    def __init__(self, args):
        self.contexts = []
        # self.indent = 0
        self.lines = []
        self.args = args
        self.current_indent = 0
        
    def push_indent(self):
        self.current_indent = self.current_indent + 1
        
    def pop_indent(self):
        self.current_indent = self.current_indent - 1
        
    def all_context_proto_names(self):
        return [context.proto_name for context in self.contexts]

    def current_context(self):
        return self.contexts[-1]

    def indent(self):
        return self.current_indent
        # return len(self.contexts)
        
    def push_context(self, proto_name, swift_name):
        self.contexts.append(WriterContext(proto_name, swift_name))
        self.push_indent()
        
    def pop_context(self):
        self.contexts.pop()
        self.pop_indent()
    
    def add(self, line):
        self.lines.append(('\t' * self.indent()) + line)
    
    def extend(self, text):
        for line in text.split('\n'):
            self.add(line)
        
    def join(self):
        lines = [line.rstrip() for line in self.lines]
        return '\n'.join(lines)
        
    def rstrip(self):
        lines = self.lines
        while len(lines) > 0 and len(lines[-1].strip()) == 0:
            lines = lines[:-1]
        self.lines = lines
        
    # def prefixed_name(self, proto_name):
    #     names = self.all_context_proto_names() + [proto_name,]
    #     return self.args.wrapper_prefix + '_'.join(names)

    def is_top_level_entity(self):
        return self.indent() == 0
        
    def newline(self):
        self.add('')


class BaseContext(object):
    def __init__(self):
        self.parent = None
        self.proto_name = None
        
    def inherited_proto_names(self):
        if self.parent is None:
            return []
        if self.proto_name is None:
            return []
        return self.parent.inherited_proto_names() + [self.proto_name,]

    def derive_swift_name(self):
        names = self.inherited_proto_names()
        return self.args.wrapper_prefix + '_'.join(names)

    def derive_wrapped_swift_name(self):
        names = self.inherited_proto_names()
        return self.args.proto_prefix + '_' + '.'.join(names)
        
    def children(self):
        return []
        
    def descendents(self):
        result = []
        for child in self.children():
            result.append(child)
            result.extend(child.descendents())
        return result
        
    def siblings(self):
        result = []
        if self.parent is not None:
            result = self.parent.children()
        return result
        
    def ancestors(self):
        result = []
        if self.parent is not None:
            result.append(self.parent)
            result.extend(self.parent.ancestors())
        return result
        
    def context_for_proto_type(self, field):
        candidates = []
        candidates.extend(self.descendents())
        candidates.extend(self.siblings())
        for ancestor in self.ancestors():
            if ancestor.proto_name is None:
                # Ignore the root context
                continue
            candidates.append(ancestor)
            candidates.extend(ancestor.siblings())

        for candidate in candidates:
            if candidate.proto_name == field.proto_type:
                return candidate
        
        return None                
        
    
    def base_swift_type_for_proto_type(self, field):
    
        if field.proto_type == 'string':
            return 'String'
        elif field.proto_type == 'uint64':
            return 'UInt64'            
        elif field.proto_type == 'uint32':
            return 'UInt32'
        elif field.proto_type == 'fixed64':
            return 'UInt64'
        elif field.proto_type == 'bool':
            return 'Bool'
        elif field.proto_type == 'bytes':
            return 'Data'
        else:
            matching_context = self.context_for_proto_type(field)
            if matching_context is not None:
                return matching_context.swift_name
            else:
                # Failure
                return field.proto_type
    
    def swift_type_for_proto_type(self, field):
        base_type = self.base_swift_type_for_proto_type(field)
        
        if field.rules == 'optional':
            can_be_optional = self.can_field_be_optional(field)
            if can_be_optional:
                return '%s?' % base_type
            else:
                return base_type
        elif field.rules == 'required':
            return base_type
        elif field.rules == 'repeated':
            return '[%s]' % base_type
        else:
            # TODO: fail
            return base_type
        
        # return 'UNKNOWN'
        
    def can_field_be_optional(self, field):
        if field.proto_type == 'uint64':
            return False
        elif field.proto_type == 'uint32':
            return False
        elif field.proto_type == 'fixed64':
            return False
        elif field.proto_type == 'bool':
            return False
        elif self.is_field_an_enum(field):
            return False
        else:
            return True
        
    def is_field_an_enum(self, field):
        matching_context = self.context_for_proto_type(field)
        if matching_context is not None:
            if type(matching_context) is EnumContext:
                return True
        return False
        
    def is_field_a_proto(self, field):
        matching_context = self.context_for_proto_type(field)
        if matching_context is not None:
            if type(matching_context) is MessageContext:
                return True
        return False


class FileContext(BaseContext):
    def __init__(self, args):
        BaseContext.__init__(self)
        
        self.args = args
        
        self.messages = []
        self.enums = []
        
    def children(self):
        return self.enums + self.messages
        
    def prepare(self):
        for child in self.children():
            child.prepare()
        
    def generate(self, writer):
        writer.extend('''//
//  Copyright (c) 2018 Open Whisper Systems. All rights reserved.
//

import Foundation
''')
        
        for child in self.children():
            child.generate(writer)


class MessageField:
    def __init__(self, name, index, rules, proto_type, field_default):
        self.name = name
        self.index = index
        self.rules = rules
        self.proto_type = proto_type
        self.field_default = field_default
            

class MessageContext(BaseContext):
    def __init__(self, args, parent, proto_name):
        BaseContext.__init__(self)

        self.args = args
        self.parent = parent
        
        self.proto_name = proto_name

        self.messages = []
        self.enums = []
        
        self.field_map = {}
    
    def fields(self):
        return self.field_map.values()
    
    def field_indices(self):
        return [field.index for field in self.fields()]

    def field_names(self):
        return [field.name for field in self.fields()]

    def children(self):
        return self.enums + self.messages
        
    def prepare(self):
        self.swift_name = self.derive_swift_name()
        
        for child in self.children():
            child.prepare()
        
    def generate(self, writer):
        is_top_level_entity = writer.is_top_level_entity()
        
        writer.add('// MARK: - %s' % self.swift_name)
        writer.newline()
        
        writer.add('@objc public class %s: NSObject {' % self.swift_name)
        writer.newline()
        
        writer.push_context(self.proto_name, self.swift_name)
        
        if is_top_level_entity:
            writer.invalid_protobuf_error_name = '%sError' % self.swift_name
            writer.extend(('''
public enum %s: Error {
    case invalidProtobuf(description: String)
}
''' % writer.invalid_protobuf_error_name).strip())
            writer.newline()
        
        for child in self.children():
            child.generate(writer)

        # Prepare fields
        for field in self.fields():
            field.type_swift = self.swift_type_for_proto_type(field)
            field.name_swift = field.name
        
        # Property Declarations
        for field in self.fields():
            writer.add('@objc public let %s: %s' % (field.name_swift, field.type_swift))
        writer.newline()
        
        # Initializer
        initializer_parameters = []
        for field in self.fields():
            initializer_parameters.append('%s: %s' % (field.name_swift, field.type_swift))
        initializer_parameters = ', '.join(initializer_parameters)
        writer.add('@objc public init(%s) {' % initializer_parameters)
        writer.push_indent()
        for field in self.fields():
            writer.add('self.%s = %s' % (field.name_swift, field.name_swift))
        writer.pop_indent()
        writer.add('}')
        writer.newline()

        # serializedData() func
        writer.extend(('''
@objc
public func serializedData() throws -> Data {
    return try self.asProtobuf.serializedData()
}
''').strip())
        writer.newline()
    
        # asProtobuf() func
        wrapped_swift_name = self.derive_wrapped_swift_name()
        writer.add('fileprivate var asProtobuf: %s {' % wrapped_swift_name)
        writer.push_indent()
        writer.add('let proto = %s.with { (builder) in' % wrapped_swift_name)
        writer.push_indent()
        for field in self.fields():
            if self.is_field_an_enum(field):
                # TODO: Assert that rules is empty.
                enum_context = self.context_for_proto_type(field)
                writer.add('builder.%s = %sUnwrap(self.%s)' % ( field.name_swift, enum_context.swift_name, field.name_swift, ) )
            elif field.rules == 'repeated':
                # TODO: Assert that type is a message.
                list_wrapped_swift_name = None
                if self.is_field_a_proto(field):
                    message_context = self.context_for_proto_type(field)
                    list_wrapped_swift_name = message_context.derive_wrapped_swift_name()
                else:
                    # TODO: Assert not an enum.
                    list_wrapped_swift_name = self.base_swift_type_for_proto_type(field)
                writer.add('var %sUnwrapped = [%s]()' % (field.name_swift, list_wrapped_swift_name))
                writer.add('for item in %s {' % (field.name_swift))
                writer.push_indent()
                if self.is_field_a_proto(field):
                    writer.add('%sUnwrapped.append(item.asProtobuf)' % field.name_swift)
                else:
                    writer.add('%sUnwrapped.append(item)' % field.name_swift)
                writer.pop_indent()
                writer.add('}')
                writer.add('builder.%s = %sUnwrapped' % (field.name_swift, field.name_swift))
            elif field.rules == 'optional' and self.can_field_be_optional(field):
                writer.add('if let %s = self.%s {' % (field.name_swift, field.name_swift))
                writer.push_indent()
                if self.is_field_a_proto(field):
                    writer.add('builder.%s = %s.asProtobuf' % (field.name_swift, field.name_swift))
                else:
                    writer.add('builder.%s = %s' % (field.name_swift, field.name_swift))
                writer.pop_indent()
                writer.add('}')
            else:
                writer.add('builder.%s = self.%s' % (field.name_swift, field.name_swift))
            writer.newline()
        #     writer.add('self.%s = %s' % (field.name_swift, field.name_swift))
        writer.rstrip()
        writer.pop_indent()
        writer.add('}')
        writer.newline()
        writer.add('return proto')
        writer.pop_indent()
        writer.add('}')
        writer.newline()
        
        writer.pop_context()

        writer.rstrip()
        writer.add('}')
        writer.newline()
        
        
class EnumContext(BaseContext):
    def __init__(self, args, parent, proto_name):
        BaseContext.__init__(self)

        self.args = args
        self.parent = parent        
        self.proto_name = proto_name
        
        # self.item_names = set()
        # self.item_indices = set()
        self.item_map = {}
    
    def derive_wrapped_swift_name(self):
        # return BaseContext.derive_wrapped_swift_name(self) + 'Enum'
        result = BaseContext.derive_wrapped_swift_name(self)
        if self.proto_name == 'Type':
            result = result + 'Enum'
        return result
    
    def item_names(self):
        return self.item_map.values()
    
    def item_indices(self):
        return self.item_map.keys()

    def prepare(self):
        self.swift_name = self.derive_swift_name()
        
        for child in self.children():
            child.prepare()

    def case_pairs(self):
        indices = [int(index) for index in self.item_indices()]
        indices = sorted(indices)
        result = []
        for index in indices:
            index_str = str(index)
            item_name = self.item_map[index_str]
            case_name = lowerCamlCaseForUnderscoredText(item_name)
            result.append( (case_name, index_str,) )
        return result

    def generate(self, writer):
        
        writer.add('// MARK: - %s' % self.swift_name)
        writer.newline()
        
        writer.add('@objc public enum %s: Int32 {' % self.swift_name)
        
        writer.push_context(self.proto_name, self.swift_name)

        for case_name, case_index in self.case_pairs():
            if case_name == 'default':
                case_name = '`default`'
            writer.add('case %s = %s' % (case_name, case_index,))
        
        writer.pop_context()

        writer.rstrip()
        writer.add('}')
        writer.newline()
        
        wrapped_swift_name = self.derive_wrapped_swift_name()
        writer.add('private func %sWrap(_ value: %s) -> %s {' % ( self.swift_name, wrapped_swift_name, self.swift_name, ) )
        writer.push_indent()
        writer.add('switch value {')
        writer.push_indent()
        for case_name, case_index in self.case_pairs():
            writer.add('case .%s: return .%s' % (case_name, case_name,))
        writer.pop_indent()
        writer.add('}')
        writer.pop_indent()
        writer.add('}')
        writer.newline()
        writer.add('private func %sUnwrap(_ value: %s) -> %s {' % ( self.swift_name, self.swift_name, wrapped_swift_name, ) )
        writer.push_indent()
        writer.add('switch value {')
        writer.push_indent()
        for case_name, case_index in self.case_pairs():
            writer.add('case .%s: return .%s' % (case_name, case_name,))
        writer.pop_indent()
        writer.add('}')
        writer.pop_indent()
        writer.add('}')
        writer.newline()
        

def line_parser(text):
    # lineParser = LineParser(text.split('\n'))
    
    for line in text.split('\n'):
        line = line.strip()
        # if not line:
        #     continue

        comment_index = line.find('//')
        if comment_index >= 0:
            line = line[:comment_index].strip()
        if not line:
            continue
        
        if args.verbose:
            print 'line:', line
            
        yield line
        

def parse_enum(args, proto_file_path, parser, parent_context, enum_name):

    if args.verbose:
        print '# enum:', enum_name
    
    context = EnumContext(args, parent_context, enum_name)
    
    while True:
        try:
            line = parser.next()
        except StopIteration:
            raise Exception('Incomplete enum: %s' % proto_file_path)
    
        if line == '}':
            if args.verbose:
                print
            parent_context.enums.append(context)
            return

        item_regex = re.compile(r'^(.+?)\s*=\s*(\d+?)\s*;$')
        item_match = item_regex.search(line)
        if item_match:
            item_name = item_match.group(1).strip()
            item_index = item_match.group(2).strip()
        
            if args.verbose:
                print '\t enum item[%s]: %s' % (item_index, item_name)
            
            if item_name in context.item_names():
                raise Exception('Duplicate enum name[%s]: %s' % (proto_file_path, item_name))
            
            if item_index in context.item_indices():
                raise Exception('Duplicate enum index[%s]: %s' % (proto_file_path, item_name))
            
            context.item_map[item_index] = item_name
                
            continue
    
        raise Exception('Invalid enum syntax[%s]: %s' % (proto_file_path, line))
        

def optional_match_group(match, index):
    group = match.group(index)
    if group is None:
        return None
    return group.strip()


def parse_message(args, proto_file_path, parser, parent_context, message_name):

    if args.verbose:
        print '# message:', message_name
    
    context = MessageContext(args, parent_context, message_name)
        
    while True:
        try:
            line = parser.next()
        except StopIteration:
            raise Exception('Incomplete message: %s' % proto_file_path)
    
        if line == '}':
            if args.verbose:
                print
            parent_context.messages.append(context)
            return

        enum_regex = re.compile(r'^enum\s+(.+?)\s+\{$')
        enum_match = enum_regex.search(line)
        if enum_match:
            enum_name = enum_match.group(1).strip()        
            parse_enum(args, proto_file_path, parser, context, enum_name)
            continue
        
        message_regex = re.compile(r'^message\s+(.+?)\s+\{$')
        message_match = message_regex.search(line)
        if message_match:
            message_name = message_match.group(1).strip()
            parse_message(args, proto_file_path, parser, context, message_name)
            continue

        # Examples:
        #
        # optional bytes  id          = 1;
        # optional bool              isComplete = 2 [default = false];
        item_regex = re.compile(r'^(optional|required|repeated)?\s*([\w\d]+?)\s+([\w\d]+?)\s*=\s*(\d+?)\s*(\[default = (true|false)\])?;$')
        item_match = item_regex.search(line)
        if item_match:
            # print 'item_rules:', item_match.groups()
            item_rules = optional_match_group(item_match, 1)
            item_type = optional_match_group(item_match, 2)
            item_name = optional_match_group(item_match, 3)
            item_index = optional_match_group(item_match, 4)
            # item_defaults_1 = optional_match_group(item_match, 5)
            item_default = optional_match_group(item_match, 6)
    
            # print 'item_rules:', item_rules
            # print 'item_type:', item_type
            # print 'item_name:', item_name
            # print 'item_index:', item_index
            # print 'item_default:', item_default
            
            message_field = {
                'rules': item_rules,
                'type': item_type,
                'name': item_name,
                'index': item_index,
                'default': item_default,
            }
            # print 'message_field:', message_field
        
            if args.verbose:
                print '\t message field[%s]: %s' % (item_index, str(message_field))
            
            if item_name in context.field_names():
                raise Exception('Duplicate message field name[%s]: %s' % (proto_file_path, item_name))
            # context.field_names.add(item_name)
            
            if item_index in context.field_indices():
                raise Exception('Duplicate message field index[%s]: %s' % (proto_file_path, item_name))
            # context.field_indices.add(item_index)
            
            context.field_map[item_index] = MessageField(item_name, item_index, item_rules, item_type, item_default)
            # context.fields.append(message_field)
                    # class MessageField:
                    #     def __init__(self, name, index, rules, field_type, field_default):
                            
            continue

        raise Exception('Invalid message syntax[%s]: %s' % (proto_file_path, line))
    
    
def process_proto_file(args, proto_file_path, dst_file_path):
    with open(proto_file_path, 'rt') as f:
        text = f.read()
    
    multiline_comment_regex = re.compile(r'/\*.*?\*/', re.MULTILINE|re.DOTALL)
    text = multiline_comment_regex.sub('', text)
    
    syntax_regex = re.compile(r'^syntax ')
    package_regex = re.compile(r'^package\s+(.+);')
    option_regex = re.compile(r'^option ')
    
    parser = line_parser(text)
    
    # lineParser = LineParser(text.split('\n'))
    
    context = FileContext(args)
    
    while True:
        try:
            line = parser.next()
        except StopIteration:
            break

        if syntax_regex.search(line):
            if args.verbose:
                print '# Ignoring syntax'
            continue
        
        if option_regex.search(line):
            if args.verbose:
                print '# Ignoring option'
            continue
        
        package_match = package_regex.search(line)
        if package_match:
            if args.package:
                raise Exception('More than one package statement: %s' % proto_file_path)
            args.package = package_match.group(1).strip()
            
            if args.verbose:
                print '# package:', args.package
            continue
        
        message_regex = re.compile(r'^message\s+(.+?)\s+\{$')
        message_match = message_regex.search(line)
        if message_match:
            message_name = message_match.group(1).strip()
            parse_message(args, proto_file_path, parser, context, message_name)
            continue
    
        raise Exception('Invalid syntax[%s]: %s' % (proto_file_path, line))
    
    writer = LineWriter(args)
    context.prepare()
    context.generate(writer)
    output = writer.join()
    with open(dst_file_path, 'wt') as f:
        f.write(output)
    
    
if __name__ == "__main__":
    
    parser = argparse.ArgumentParser(description='Protocol Buffer Swift Wrapper Generator.')
    # parser.add_argument('--all', action='store_true', help='process all files in or below current dir')
    # parser.add_argument('--path', help='used to specify a path to a file.')
    parser.add_argument('--proto-dir', help='dir path of the proto schema file.')
    parser.add_argument('--proto-file', help='filename of the proto schema file.')
    parser.add_argument('--wrapper-prefix', help='name prefix for generated wrappers.')
    parser.add_argument('--proto-prefix', help='name prefix for proto bufs.')
    parser.add_argument('--dst-dir', help='path to the destination directory.')
    parser.add_argument('--verbose', action='store_true', help='enables verbose logging')
    args = parser.parse_args()
    
    if args.verbose:
        print 'args:', args
    
    proto_file_path = os.path.abspath(os.path.join(args.proto_dir, args.proto_file))
    if not os.path.exists(proto_file_path):
        raise Exception('File does not exist: %s' % proto_file_path)
    
    dst_dir_path = os.path.abspath(args.dst_dir)
    if not os.path.exists(dst_dir_path):
        raise Exception('Destination does not exist: %s' % dst_dir_path)
    
    dst_file_path = os.path.join(dst_dir_path, "%s.swift" % args.wrapper_prefix)
    
    if args.verbose:
        print 'dst_file_path:', dst_file_path
    
    args.package = None
    process_proto_file(args, proto_file_path, dst_file_path)
    
    print 'complete.'
    