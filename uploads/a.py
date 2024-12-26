def is_lucky_number(num):
    return all(digit in '47' for digit in str(num))

def count_lucky_digits(n):
    return sum(1 for digit in str(n) if digit in '47')

n = int(input())
lucky_digit_count = count_lucky_digits(n)

if is_lucky_number(lucky_digit_count):
    print("YES")
else:
    print("NO")