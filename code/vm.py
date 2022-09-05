from algebra import *
from io_table import IOTable
from instruction_table import InstructionTable
from memory_table import MemoryTable
from multivariate import *
import sys

from processor_table import ProcessorTable

# `Getch` shamelessly copied from https://stackoverflow.com/a/510364/2574407


class _Getch:
    """Gets a single character from standard input.  Does not echo to the
screen."""

    def __init__(self):
        try:
            self.impl = _GetchWindows()
        except ImportError:
            self.impl = _GetchUnix()

    def __call__(self): return self.impl()


class _GetchUnix:
    def __init__(self):
        import tty
        import sys

    def __call__(self):
        import sys
        import tty
        import termios
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(sys.stdin.fileno())
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return ch


class _GetchWindows:
    def __init__(self):
        import msvcrt

    def __call__(self):
        import msvcrt
        return msvcrt.getch()


getch = _Getch()


class Register:
    field = BaseField.main()

    def __init__(self):
        self.cycle = Register.field.zero()
        self.instruction_pointer = Register.field.zero()
        self.current_instruction = Register.field.zero()
        self.next_instruction = Register.field.zero()
        self.memory_pointer = Register.field.zero()
        self.memory_value = Register.field.zero()
        self.memory_value_inverse = Register.field.zero()


class VirtualMachine:
    field = BaseField.main()

    def execute(brainfuck_code):
        program = VirtualMachine.compile(brainfuck_code)
        running_time, input_data, output_data = VirtualMachine.run(program)
        return running_time, input_data, output_data

    def compile(brainfuck_code):

        # shorthands
        field = VirtualMachine.field
        zero = field.zero()
        one = field.one()
        def F(x): return BaseFieldElement(ord(x), field)

        # parser
        program = []
        # keeps track of loop beginnings while (potentially nested) loops are being compiled
        stack = []
        for symbol in brainfuck_code:
            program += [F(symbol)]
            # to allow skipping a loop and jumping back to the loop's beginning, the respective start and end positions
            # are recorded in the program. For example, the (nonsensical) program `+[>+<-]+` would be `+[9>+<-]3+`.
            if symbol == '[':
                # placeholder for position of loop's end, to be filled in once position is known
                program += [zero]
                stack += [len(program) - 1]
            elif symbol == ']':
                # record loop's end
                program += [BaseFieldElement(stack[-1] + 1, field)]
                # record loop's beginning
                program[stack[-1]] = BaseFieldElement(len(program), field)
                stack = stack[:-1]

        return program

    def run(program, input_data=[]):
        # shorthands
        field = VirtualMachine.field
        zero = field.zero()
        one = field.one()
        def F(x): return BaseFieldElement(ord(x), field)

        # initial state
        instruction_pointer = 0
        memory_pointer = BaseFieldElement(0, VirtualMachine.field)
        memory = dict()  # field elements to field elements
        output_data = []
        input_counter = 0

        # main loop
        running_time = 1
        while instruction_pointer < len(program):
            if program[instruction_pointer] == F('['):
                if memory.get(memory_pointer, zero) == zero:
                    instruction_pointer = program[instruction_pointer + 1].value
                else:
                    instruction_pointer += 2
            elif program[instruction_pointer] == F(']'):
                if memory.get(memory_pointer, zero) != zero:
                    instruction_pointer = program[instruction_pointer + 1].value
                else:
                    instruction_pointer += 2
            elif program[instruction_pointer] == F('<'):
                instruction_pointer += 1
                memory_pointer -= one
            elif program[instruction_pointer] == F('>'):
                instruction_pointer += 1
                memory_pointer += one
            elif program[instruction_pointer] == F('+'):
                instruction_pointer += 1
                memory[memory_pointer] = memory.get(memory_pointer, zero) + one
            elif program[instruction_pointer] == F('-'):
                instruction_pointer += 1
                memory[memory_pointer] = memory.get(memory_pointer, zero) - one
            elif program[instruction_pointer] == F('.'):
                instruction_pointer += 1
                output_data += chr(int(memory[memory_pointer].value % 256))
            elif program[instruction_pointer] == F(','):
                instruction_pointer += 1
                if input_counter < len(input_data):
                    char = input_data[input_counter]
                    input_counter += 1
                else:
                    char = getch()
                    input_data += [char]
                    input_counter += 1
                memory[memory_pointer] = BaseFieldElement(ord(char), field)
            else:
                assert (
                    False), f"unrecognized instruction at {instruction_pointer}: {program[instruction_pointer].value}"

            running_time += 1

        return running_time, input_data, output_data

    '''
    Does the same thing as `run`, but records more stuff throughout the execution. In particular, everything that's
    needed for costructing a STARK proof.
    '''

    @staticmethod
    def simulate(program, input_data=[]):
        # shorthands
        field = VirtualMachine.field
        zero = field.zero()
        one = field.one()
        two = BaseFieldElement(2, field)
        def F(x): return BaseFieldElement(ord(x), field)

        # initial state
        register = Register()
        register.current_instruction = program[0]
        if len(program) == 1:
            register.next_instruction = zero
        else:
            register.next_instruction = program[1]
        memory = dict()  # field elements to field elements
        input_counter = 0
        output_data = []

        # prepare tables
        processor_matrix = []
        instruction_matrix = [[BaseFieldElement(i, field), program[i], program[i+1]] for i in range(len(program)-1)] + \
            [[BaseFieldElement(
                len(program)-1, field), program[-1], field.zero()]]

        input_matrix = []
        output_matrix = []

        # main loop
        while register.instruction_pointer.value < len(program):
            # collect values to add new rows in execution tables
            processor_matrix += [[register.cycle,
                                  register.instruction_pointer,
                                  register.current_instruction,
                                  register.next_instruction,
                                  register.memory_pointer,
                                  register.memory_value,
                                  register.memory_value_inverse]]

            instruction_matrix += [[register.instruction_pointer,
                                    register.current_instruction,
                                    register.next_instruction]]

            # update pointer registers according to instruction
            if register.current_instruction == F('['):
                if register.memory_value == zero:
                    register.instruction_pointer = program[register.instruction_pointer.value + 1]
                else:
                    register.instruction_pointer += two

            elif register.current_instruction == F(']'):
                if register.memory_value != zero:
                    register.instruction_pointer = program[register.instruction_pointer.value + 1]
                else:
                    register.instruction_pointer += two

            elif register.current_instruction == F('<'):
                register.instruction_pointer += one
                register.memory_pointer -= one

            elif register.current_instruction == F('>'):
                register.instruction_pointer += one
                register.memory_pointer += one

            elif register.current_instruction == F('+'):
                register.instruction_pointer += one
                memory[register.memory_pointer] = memory.get(
                    register.memory_pointer, zero) + one

            elif register.current_instruction == F('-'):
                register.instruction_pointer += one
                memory[register.memory_pointer] = memory.get(
                    register.memory_pointer, zero) - one

            elif register.current_instruction == F('.'):
                register.instruction_pointer += one
                output_matrix += [
                    [memory.get(register.memory_pointer, zero)]]
                output_data += chr(
                    int(memory.get(register.memory_pointer, zero).value % 256))

            elif register.current_instruction == F(','):
                register.instruction_pointer += one
                if input_data:
                    char = input_data[input_counter]
                    input_counter += 1
                else:
                    char = getch()
                memory[register.memory_pointer] = BaseFieldElement(
                    ord(char), field)
                input_matrix += [[memory[register.memory_pointer]]]

            else:
                assert (
                    False), f"unrecognized instruction at {register.instruction_pointer.value}: '{chr(register.current_instruction.value)}'"

            # update non-pointer registers
            register.cycle += one

            if register.instruction_pointer.value < len(program):
                register.current_instruction = program[register.instruction_pointer.value]
            else:
                register.current_instruction = zero
            if register.instruction_pointer.value < len(program)-1:
                register.next_instruction = program[register.instruction_pointer.value + 1]
            else:
                register.next_instruction = zero

            register.memory_value = memory.get(register.memory_pointer, zero)

            if register.memory_value.is_zero():
                register.memory_value_inverse = zero
            else:
                register.memory_value_inverse = register.memory_value.inverse()

        # collect final state into execution tables
        processor_matrix += [[register.cycle,
                              register.instruction_pointer,
                              register.current_instruction,
                              register.next_instruction,
                              register.memory_pointer,
                              register.memory_value,
                              register.memory_value_inverse]]

        instruction_matrix += [[register.instruction_pointer,
                                register.current_instruction,
                                register.next_instruction]]

        # sort by instruction address
        instruction_matrix.sort(key=lambda row: row[0].value)

        memory_matrix = MemoryTable.derive_matrix(processor_matrix)

        return processor_matrix, memory_matrix, instruction_matrix, input_matrix, output_matrix

    @ staticmethod
    def num_challenges():
        return 11

    @ staticmethod
    def evaluation_terminal(vector, alpha):
        xfield = alpha.field
        acc = xfield.zero()
        for v in vector:
            acc = alpha * acc + xfield.lift(v)
        return acc

    @ staticmethod
    def program_evaluation(program, a, b, c, eta):
        field = program[0].field
        xfield = a.field
        running_sum = xfield.zero()
        previous_address = -xfield.one()
        padded_program = [xfield.lift(p)
                          for p in program] + [xfield.zero()]
        for i in range(len(padded_program)-1):
            address = xfield.lift(BaseFieldElement(i, field))
            current_instruction = padded_program[i]
            next_instruction = padded_program[i+1]
            if previous_address != address:
                running_sum = running_sum * eta + a * address + \
                    b * current_instruction + c * next_instruction
            previous_address = address

        index = len(padded_program)-1
        address = xfield.lift(BaseFieldElement(index, field))
        current_instruction = padded_program[index]
        next_instruction = xfield.zero()
        running_sum = running_sum * eta + a * address + \
            b * current_instruction + c * next_instruction

        return running_sum

