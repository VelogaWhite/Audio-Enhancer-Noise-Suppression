library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use IEEE.NUMERIC_STD.ALL;

entity clk_en_gen is
    generic (
        CLK_FREQ_HZ    : integer := 50000000;
        SAMPLE_RATE_HZ : integer := 16000
    );
    port (
        clk_50m     : in  std_logic;
        rst_n       : in  std_logic;
        sample_tick : out std_logic;
        probe_out   : out std_logic
    );
end entity clk_en_gen;

architecture Behavioral of clk_en_gen is
    -- 50 MHz / 16 kHz = 3125 clock cycles
    constant DIV_LIMIT : integer := CLK_FREQ_HZ / SAMPLE_RATE_HZ;
    signal count       : integer range 0 to DIV_LIMIT - 1 := 0;
    signal probe_reg   : std_logic := '0';
begin

    process(clk_50m, rst_n)
    begin
        if rst_n = '0' then
            count       <= 0;
            sample_tick <= '0';
            probe_reg   <= '0';
        elsif rising_edge(clk_50m) then
            if count = DIV_LIMIT - 1 then
                count       <= 0;
                sample_tick <= '1';
                probe_reg   <= not probe_reg; -- Toggle creates 8 kHz square wave for scope
            else
                count       <= count + 1;
                sample_tick <= '0';
            end if;
        end if;
    end process;

    probe_out <= probe_reg;

end architecture Behavioral;