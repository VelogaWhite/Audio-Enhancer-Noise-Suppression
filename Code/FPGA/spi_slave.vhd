library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use IEEE.NUMERIC_STD.ALL;

entity spi_slave is
    port (
        clk_50m   : in  std_logic;
        rst_n     : in  std_logic;
        spi_sck   : in  std_logic;
        spi_cs    : in  std_logic;
        spi_mosi  : in  std_logic;
        spi_miso  : out std_logic;
        
        -- Interface to BRAM Read Port
        rd_addr   : out std_logic_vector(9 downto 0);
        rd_data   : in  std_logic_vector(15 downto 0)
    );
end entity spi_slave;

architecture Behavioral of spi_slave is
    signal sck_sync  : std_logic_vector(2 downto 0) := (others => '1');
    signal cs_sync   : std_logic_vector(2 downto 0) := (others => '1');
    signal addr_reg  : unsigned(9 downto 0) := (others => '0');
    signal shift_reg : std_logic_vector(15 downto 0) := (others => '0');
    signal bit_cnt   : integer range 0 to 15 := 15;
begin

    rd_addr <= std_logic_vector(addr_reg);

    -- SPI Mode 0: ส่ง Bit 15 ออกทันทีที่ CS เป็น LOW เพื่อให้พร้อมรับขอบขาขึ้นแรกของ SCK
    spi_miso <= shift_reg(15) when cs_sync(1) = '0' else '0';

    process(clk_50m, rst_n)
        variable sck_falling : boolean;
        variable cs_falling  : boolean;
    begin
        if rst_n = '0' then
            sck_sync  <= (others => '1');
            cs_sync   <= (others => '1');
            addr_reg  <= (others => '0');
            shift_reg <= (others => '0');
            bit_cnt   <= 15;
        elsif rising_edge(clk_50m) then
            -- ป้องกัน Metastability 3 สเตจ
            sck_sync <= sck_sync(1 downto 0) & spi_sck;
            cs_sync  <= cs_sync(1 downto 0) & spi_cs;

            sck_falling := (sck_sync(2 downto 1) = "10");
            cs_falling  := (cs_sync(2 downto 1) = "10");

            if cs_sync(1) = '1' then
                -- บัสว่าง (Idle): ชี้ Address ไปที่ 0 เพื่อให้ BRAM ดึง Sample 0 มารอที่ rd_data
                addr_reg  <= (others => '0');
                bit_cnt   <= 15;
                shift_reg <= rd_data;
            elsif cs_falling then
                -- เริ่มต้นเฟรม (ขอบขาตกของ CS): ล็อก Sample 0 เข้า shift_reg และเลื่อน Address ไปรอที่ 1
                shift_reg <= rd_data;
                addr_reg  <= to_unsigned(1, 10);
                bit_cnt   <= 15;
            else
                -- ขอบขาตกของ SCK: เลื่อนบิตเตรียมไว้ให้ ESP32 อ่านในขอบขาขึ้นถัดไป
                if sck_falling then
                    if bit_cnt = 0 then
                        bit_cnt   <= 15;
                        shift_reg <= rd_data;      -- โหลด Sample ถัดไปเข้าชิฟต์รีจิสเตอร์
                        addr_reg  <= addr_reg + 1; -- เลื่อน Address นำหน้าไว้ 1 สเต็ปสำหรับรอบถัดไป
                    else
                        bit_cnt   <= bit_cnt - 1;
                        shift_reg <= shift_reg(14 downto 0) & '0';
                    end if;
                end if;
            end if;
        end if;
    end process;

end architecture Behavioral;