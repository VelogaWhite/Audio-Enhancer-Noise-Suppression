library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use IEEE.NUMERIC_STD.ALL;

entity audio_generator is
    port (
        clk_50m     : in  std_logic;
        rst_n       : in  std_logic;
        sample_tick : in  std_logic;
        audio_out   : out std_logic_vector(15 downto 0)
    );
end entity audio_generator;

architecture Behavioral of audio_generator is
    -- 4 บิต = 16 ขั้น (16000 Hz / 16 = 1000 Hz)
    signal phase_acc : unsigned(3 downto 0) := (others => '0');
begin

    process(clk_50m, rst_n)
    begin
        if rst_n = '0' then
            phase_acc <= (others => '0');
            audio_out <= (others => '0');
        elsif rising_edge(clk_50m) then
            if sample_tick = '1' then
                phase_acc <= phase_acc + 1;
                -- เลื่อนบิตไปทางซ้าย 8 ตำแหน่ง (คูณ 256) ช่วงสัญญาณ 0-3840 บวก DC Offset 1500
                audio_out <= std_logic_vector(resize(unsigned(phase_acc & "00000000"), 16) + 1500);
            end if;
        end if;
    end process;

end architecture Behavioral;