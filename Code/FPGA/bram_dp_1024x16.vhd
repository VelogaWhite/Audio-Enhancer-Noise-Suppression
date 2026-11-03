library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use IEEE.NUMERIC_STD.ALL;

entity bram_dp_1024x16 is
    port (
        clk     : in  std_logic;
        we      : in  std_logic;
        bank_w  : in  std_logic;
        addr_w  : in  std_logic_vector(9 downto 0);
        data_w  : in  std_logic_vector(15 downto 0);
        bank_r  : in  std_logic;
        addr_r  : in  std_logic_vector(9 downto 0);
        data_r  : out std_logic_vector(15 downto 0)
    );
end entity bram_dp_1024x16;

architecture Behavioral of bram_dp_1024x16 is
    -- 2048 words (Bank 0: 0..1023, Bank 1: 1024..2047)
    type ram_type is array (0 to 2047) of std_logic_vector(15 downto 0);
    signal ram : ram_type := (others => (others => '0'));
    
    -- Force Quartus to infer dedicated embedded M9K Block RAM
    attribute ramstyle : string;
    attribute ramstyle of ram : signal is "M9K";
    
    signal full_addr_w : std_logic_vector(10 downto 0);
    signal full_addr_r : std_logic_vector(10 downto 0);
begin

    full_addr_w <= bank_w & addr_w;
    full_addr_r <= bank_r & addr_r;

    -- Write Port (Triggered by sample_tick)
    process(clk)
    begin
        if rising_edge(clk) then
            if we = '1' then
                ram(to_integer(unsigned(full_addr_w))) <= data_w;
            end if;
        end if;
    end process;

    -- Read Port (Synchronous read for SPI Slave)
    process(clk)
    begin
        if rising_edge(clk) then
            data_r <= ram(to_integer(unsigned(full_addr_r)));
        end if;
    end process;

end architecture Behavioral;