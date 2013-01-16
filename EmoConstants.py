#
# EmoConstants - extract the Emotive constants from their header files
#
# Originally by John DiMatteo <jdimatteo@gmail.com>
# 
#   4July12 fp  woot
#   fall12 fp - fixes for MIT et al.
#

class EmoConstants(object):
    def __init__(self):
        # map #define and enum constants (in C header files) to values
        self.constants = {}
        # map #define and enum constants to either comments (for #define) or
        # to enum typedef name
        self.constant_descriptions = {}

        # note that I copy my .h into a nice local place to make it easier to use the Emotiv libraries. 
        # but
        # on the mac, they get automatically installed /Applications/EmotivResearch/docs/Examples/Xcode/include
        # which is stupid and Emotiv should be ashamed.
        #        self.add('/usr/local/include/edkErrorCode.h')
        #        self.add('/usr/local/include/edk.h')
        #        self.add('/usr/local/include/EmoStateDLL.h')
                
        self.add('edkErrorCode.h')
        self.add('edk.h')
        self.add('EmoStateDLL.h')
        
        
    def __getitem__(self, constant):
        return self.constants[constant] 

    # read in a C header file and store the #define constants in a dictionary
    # also read in enums taking advantage of Emotiv's consistent style
    # hopefully the header files don't change much, because this func is a
    # brittle mess
    def add(self, path):
        previous_line = ''
        enum_mode = False
        current_enum_description = '' 
        current_enum_value = 0
        current_bitwise_or = None 
        with open(path, 'r') as f:
            for line in f:
                if line.startswith('#define'):
                    split = line.split()
                    if len(split) == 3:
                        try:
                            self.constants[split[1]] = int(split[2], base=0)
                            comment_preface = '//!'
                            if previous_line.startswith(comment_preface):
                                comment = previous_line[len(comment_preface):].strip()
                            else:
                                comment = "No description available"
                            self.constant_descriptions[split[1]] = comment
                        except ValueError:
                            # just skip the define if it isn't for an integer
                            pass
                    elif len(split) == 2: 
                        # e.g. skip include guards
                        pass
                    else:
                        raise Exception('Unexpected line pattern: ' + line)
                elif not enum_mode and line.lstrip().startswith('typedef enum'):
                    split = line.split()
                    if len(split) < 3:
                        raise Exception("Unexpected enum formatting line: " + 
                            line)
                    enum_mode = True
                    current_enum_description = split[2] 
                elif enum_mode and line.lstrip().startswith('}'):
                    enum_mode = False 
                    # reset default staring enumerated value back to 0
                    current_enum_value = 0
                elif enum_mode and current_bitwise_or is None:
                    if '}' in line:
                        line = line[:line.find('}')]
                        enum_mode = False 
                    # there could be one or more variables on this line
                    for variable in line.split(','): 
                        split = variable.split()
                        if len(split) == 0:
                            pass
                        elif len(split) == 1:
                            self.constants[split[0]] = current_enum_value
                            self.constant_descriptions[split[0]] = current_enum_description 
                            current_enum_value = current_enum_value + 1
                        elif len(split) == 3 and split[1] == "=":
                            current_enum_value = int(split[2], base=0)
                            self.constants[split[0]] = current_enum_value 
                            self.constant_descriptions[split[0]] = current_enum_description 
                        elif len(split) > 4 and split[1] == "=" and split[3] == "|":
                            value = 0
                            for operand in "".join(split[2:]).split("|"):
                                if operand == "":
                                    # this happens when last char in line is |
                                    current_bitwise_or = split[0] 
                                else:
                                    value = value | self.constants[operand]
                            self.constants[split[0]] = value 
                            self.constant_descriptions[split[0]] = current_enum_description 
                        else:
                            raise Exception("Unexpected enum formatting" +
                                "line: " + line)
                elif enum_mode and current_bitwise_or is not None:
                    value = self.constants[current_bitwise_or] 
                    for operand in line.split("|"):
                        value = value | self.constants[operand.strip()]
                    self.constants[current_bitwise_or] = value 
                    current_bitwise_or = None

                previous_line = line

    def describe(self, constant, enum_type = None):
        possible_names = [name for name, value in self.constants.items() if value == constant]
        possible_descriptions = [self.constant_descriptions[name] for name in possible_names]
        description = None
        for (name, name_description) in zip(possible_names, possible_descriptions):
            if enum_type is not None and enum_type != name_description:
                continue
            name_with_description = name + ' "' + name_description + '"' 
            if description is None:
                description = name_with_description 
            else:
                description = description + ', or ' + name_with_description 
        return description 
