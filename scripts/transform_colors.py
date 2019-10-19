import re
import numpy as np
from scipy.optimize import minimize
from colormath.color_conversions import convert_color
from colormath.color_objects import sRGBColor, HSLColor
import webcolors

# Script to transform all colors
#
# Run this script from the main project directory.
# This script will read the .mss files whose names are specified in the variable 'mss_files' below;
# these source .mss files should be in the subdirectory 'mss'.
# It will generate modified .mss files in the main project directory.
# All colors will be transformed with the function t(x) below.
# Here x is an R, G, or B value from 0 to 1, and t(x) returns the transformed value.
# The percentage parameters for functions such as darken, saturate, and scale-hsla will be recomputed
# so that the resulting colors most closely match the desired t(x) transformation.

mss_files = [
    'style',
    'landcover',
    'water',
    'water-features',
    'road-colors-generated',
    'roads',
    'power',
    'admin',
    'placenames',
    'buildings',
    'stations',
    'amenity-points',
    'ferry-routes',
    'aerialways',
    'addressing'
]

VARIABLE = r'@[\w\-_]+'
VARIABLE_DEF = r'\s*(@[\w\-_]+)\s*:(.+);'
HEX_COLOR = r'#[\da-fA-F]+\b'
FUNCTION = r'\b(?!mix)(\w+)\((.+),\s*(.+)%\s*\)'
MIX_FUNCTION = r'\bmix\((\w+\([^\(\)]+\)),\s*(\w+\([^\(\)]+\)),\s*(.+)%\s*\)'
RGBA = r'rgba\(.+\)'
NAMED_COLOR = r'[A-Za-z]+'
SCALE_L = r'scale-hsla\(\s*0\s*,\s*1\s*,\s*0\s*,\s*1\s*,\s*([\d\.]+)\s*,\s*([\d\.]+)\s*,\s*0\s*,\s*1\s*\)'

variables = {}

def t(x):
    return x**1.6 + 1/15 if x < 0.9377 else (x - 1)/2 + 1

def t_rgb(rgb):
    return sRGBColor(t(rgb.clamped_rgb_r), t(rgb.clamped_rgb_g), t(rgb.clamped_rgb_b))

def lighten(rgb, amount):
    hsl = convert_color(rgb, HSLColor)
    hsl_new = HSLColor(hsl.hsl_h, hsl.hsl_s, np.clip(hsl.hsl_l + amount/100, 0, 1))
    return convert_color(hsl_new, sRGBColor)

def darken(rgb, amount):
    return lighten(rgb, -amount)

def saturate(rgb, amount):
    hsl = convert_color(rgb, HSLColor)
    hsl_new = HSLColor(hsl.hsl_h, np.clip(hsl.hsl_s + amount/100, 0, 1), hsl.hsl_l)
    return convert_color(hsl_new, sRGBColor)

def desaturate(rgb, amount):
    return saturate(rgb, -amount)

def scale_l(rgb, l0, l1):
    hsl = convert_color(rgb, HSLColor)
    hsl_new = HSLColor(hsl.hsl_h, hsl.hsl_s, l0 + hsl.hsl_l * (l1 - l0))
    return convert_color(hsl_new, sRGBColor)

class Variable:
    def __init__(self, name, value):
        self.name = name
        self.value = value
    
    def __repr__(self):
        return f'Variable({self.name}, {repr(self.value)})'
    
    def print_definition(self):
        if isinstance(self.value, sRGBColor):
            col = self.value
            col1 = t_rgb(col)
            definition = col1.get_rgb_hex()
        elif isinstance(self.value, str):
            definition = self.value
        elif isinstance(self.value, Function):
            definition = self.value.print_transform()
        else:
            definition = ''
        return self.name + ': ' + definition

class Function:
    def __init__(self, name, argument, value):
        self.name = name
        self.argument = parse_definition(argument)
        self.value = value

    def __repr__(self):
        return f'Function({self.name}, {repr(self.argument)}, {repr(self.value)})'

    def eval(self):
        if not isinstance(self.argument, str):
            return None
        arg = variables[self.argument].value
        fun = globals()[self.name]
        return fun(arg, int(self.value))
    
    def print_transform(self):
        if isinstance(self.argument, Function):
            fun1 = self.argument.name
            val1 = int(self.argument.value)
            fun2 = self.name
            val2 = int(self.value)
            arg = self.argument.argument
            val1, val2 = transform_2fun(fun1, val1, fun2, val2, arg)
            return f'{fun2}({fun1}({arg}, {round(float(val1))}%), {round(float(val2))}%)'

        fun = self.name
        val = int(self.value)
        arg = self.argument
        val = transform_fun(fun, val, arg)[0]
        if isinstance(arg, sRGBColor):
            arg = t_rgb(arg).get_rgb_hex()
        return f'{fun}({arg}, {round(float(val))}%)'

def transform_fun(fun_str, val, arg):
    while isinstance(arg, str):
        arg = variables[arg].value
    if isinstance(arg, Function):
        arg = arg.eval()
    fun = globals()[fun_str]
    res = fun(arg, val)
    arg_t = t_rgb(arg)
    res_t_goal = t_rgb(res)

    def minfun(x):
         res_t = fun(arg_t, x[0])
         return np.linalg.norm((
             res_t.rgb_r - res_t_goal.rgb_r,
             res_t.rgb_g - res_t_goal.rgb_g,
             res_t.rgb_b - res_t_goal.rgb_b,
             ))
    
    x0 = np.array([val])
    min_res = minimize(minfun, x0, method='nelder-mead', options={'xtol': 1e-6, 'disp': True})
    return min_res.x

def transform_2fun(fun1_str, val1, fun2_str, val2, arg):
    while isinstance(arg, str):
        arg = variables[arg].value
    if isinstance(arg, Function):
        arg = arg.eval()
    fun1 = globals()[fun1_str]
    fun2 = globals()[fun2_str]
    res = fun2(fun1(arg, val1), val2)
    arg_t = t_rgb(arg)
    res_t_goal = t_rgb(res)

    def minfun(x):
         res_t = fun2(fun1(arg_t, x[0]), x[1])
         return np.linalg.norm((
             res_t.rgb_r - res_t_goal.rgb_r,
             res_t.rgb_g - res_t_goal.rgb_g,
             res_t.rgb_b - res_t_goal.rgb_b,
             ))
    
    x0 = np.array([val1, val2])
    min_res = minimize(minfun, x0, method='nelder-mead', options={'xtol': 1e-6, 'disp': True})
    return min_res.x

def transform_scale_l(l0, l1):
    if l0 == 0 and l1 == 1:
        return 'scale-hsla(0,1,0,1,0,   1,   0,1)'
    color_names = ('@forest', '@grass', '@farmland', '@residential')
    colors = [variables[name].value for name in color_names]
    res = [scale_l(color, l0, l1) for color in colors]
    colors_t = [t_rgb(color) for color in colors]
    res_t_goal = [t_rgb(color) for color in res]

    def minfun(x):
        res_t = [scale_l(color, x[0], x[1]) for color in colors_t]
        norms = [np.linalg.norm((
             res_t_item.rgb_r - res_t_goal_item.rgb_r,
             res_t_item.rgb_g - res_t_goal_item.rgb_g,
             res_t_item.rgb_b - res_t_goal_item.rgb_b,
             ))
             for res_t_item, res_t_goal_item in zip(res_t, res_t_goal)
        ]
        return sum(norms)

    x0 = np.array([l0, l1])
    l0, l1 = minimize(minfun, x0, method='nelder-mead', options={'xtol': 1e-6, 'disp': True}).x

    return f'scale-hsla(0,1,0,1,{l0:.2},{l1:.2},0,1)'

def parse_var_def(variable_name, definition):
    definition = parse_definition(definition)
    return Variable(variable_name, definition)

def parse_hex_color(match):
    c = match.group()
    if len(c) == 4:
        c = f'#{c[1]}{c[1]}{c[2]}{c[2]}{c[3]}{c[3]}'
    return sRGBColor.new_from_rgb_hex(c)

def parse_function(match):
    name = match.group(1)
    argument = match.group(2)
    value = match.group(3)
    return Function(name, argument, value)

def parse_definition(definition):
    match = re.match(HEX_COLOR, definition)
    if match:
        return parse_hex_color(match)

    match = re.match(RGBA, definition)
    if match:
        return definition

    match = re.match(FUNCTION, definition)
    if match:
        return parse_function(match)

    match = re.match(VARIABLE, definition)
    if match:
        return definition

    match = re.match(NAMED_COLOR, definition)
    if match:
        try:
            color = webcolors.name_to_hex(definition)
            return sRGBColor.new_from_rgb_hex(color)
        except ValueError:
            pass

    return definition

def transform():
    def fun_repl(match):
        return parse_function(match).print_transform()

    def mix_fun_repl(match):
        match1 = re.match(FUNCTION, match.group(1))
        match2 = re.match(FUNCTION, match.group(2))
        return 'mix(' + parse_function(match1).print_transform() + ', ' + parse_function(match2).print_transform() + ', ' + match.group(3) + '%)'

    def color_repl(match):
        return t_rgb(parse_hex_color(match)).get_rgb_hex()

    def scale_l_repl(match):
        return transform_scale_l(float(match.group(1)), float(match.group(2)))

    for filename in mss_files:
        with open('mss/' + filename + '.mss', 'r') as infile, open(filename + '.mss', 'w') as outfile:
            for line in infile:
                match = re.match(VARIABLE_DEF, line)
                if match:
                    var = parse_var_def(match.group(1), match.group(2).strip())
                    variables[match.group(1)] = var
                    outfile.write(var.print_definition() + ';\n')
                else:
                    match = re.search(SCALE_L, line)
                    if match:
                        line = re.sub(SCALE_L, scale_l_repl, line)
                    else:
                        match = re.search(MIX_FUNCTION, line)
                        if match:
                            line = re.sub(MIX_FUNCTION, mix_fun_repl, line)
                        else:
                            match = re.search(FUNCTION, line)
                            if match:
                                line = re.sub(FUNCTION, fun_repl, line)
                            else:
                                line = re.sub(HEX_COLOR, color_repl, line)
                    outfile.write(line)

transform()
print('Done')