/* Independent ET_REL module, explicit Thumb initializer first. */
SECTIONS
{
 .text : { KEEP(*(.text.watch6_entry)) *(.text .text.*) }
 .rodata : { *(.rodata .rodata.*) }
 .data : { *(.data .data.*) }
 .bss : { *(.bss .bss.* COMMON) }
 .init_array : { *(.init_array .init_array.*) }
 .fini_array : { *(.fini_array .fini_array.*) }
}
