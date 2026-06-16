global main

extern printf
extern clock

section .data
    fmt_sum  db "sum = %llu",10,0
    fmt_time db "time = %.6f s",10,0

section .text

main:
    push r12
    push rbx

    ; clock start
    call clock
    mov r12, rax

    ; sum = 0
    xor rbx, rbx
    xor rcx, rcx

.loop:
    mov rax, rcx
    imul rax, 17

    mov rdx, rcx
    shr rdx, 3

    xor rax, rdx
    add rbx, rax

    inc rcx
    cmp rcx, 1000000000
    jne .loop

    ; elapsed ticks
    call clock
    sub rax, r12
    mov r12, rax

    ; printf("sum = %llu\n", sum)
    lea rdi, [rel fmt_sum]
    mov rsi, rbx
    xor eax, eax
    call printf

    ; double seconds = elapsed / 1000000.0
    cvtsi2sd xmm0, r12

    mov rax, 1000000
    cvtsi2sd xmm1, rax

    divsd xmm0, xmm1

    ; printf("time = %.6f s\n", seconds)
    lea rdi, [rel fmt_time]
    mov eax, 1          ; 1 vector argument in xmm0
    call printf

    xor eax, eax

    pop rbx
    pop r12
    ret